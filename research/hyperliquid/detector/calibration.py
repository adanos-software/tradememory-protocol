"""Synthetic calibration: Type-I / power / latency measurement + grid search.

Pure Python, no numpy/scipy.  All randomness is seeded deterministically.

Public API
----------
measure(cfg, anchors, cov, delta, n_streams, length, seed)
    -> dict with keys "type_i", "power", "median_detection_latency_buckets"

lda_weights(axis, anchors, cov, delta, seed)
    -> dict[primitive, float]  sum|w| == 1

grid_search(anchors, cov, seed, n_streams, ...)
    -> list[dict]  one row per hyper-param combo

pick_winner(rows)
    -> (winner_or_None, typeI_target_relaxed_bool)

run_calibration(anchors, cov, seed, n_streams, out_path, ...)
    -> artifact dict  (also written as JSON to out_path)

Import-isolation: only stdlib + math + random + research.hyperliquid.*.
No numpy, no scipy, no tradememory.owm.*.
"""
from __future__ import annotations

import json
import math
import random

from research.hyperliquid.detector.config import (
    AXES,
    BAD_DIR,
    PRIMITIVES,
    BaselineStats,
    DetectorConfig,
    PrimitiveStats,
)
from research.hyperliquid.detector.hmm_synth import SynthSpec, generate_stream
from research.hyperliquid.detector.detector import run_detector_on_stream

# ---------------------------------------------------------------------------
# internal constants
# ---------------------------------------------------------------------------
_LARGE_N = 100_000        # sentinel n for "effectively infinite" baseline stats
_SIGMA_FLOOR = 1e-9       # avoid division by zero in LDA / z-scoring


# ---------------------------------------------------------------------------
# baseline builder (key wiring note from spec)
# ---------------------------------------------------------------------------

def _baseline_from_anchors(anchors: dict) -> BaselineStats:
    """Build a BaselineStats where self == universe, both set to anchors.

    For each axis/primitive: mean = anchors[axis][p]["median"],
                             std  = anchors[axis][p]["mad"].

    This ensures that a Drifting emission at median + delta*mad z-scores to
    approximately delta (BAD_DIR-signed), which is what drives detection.
    """
    stats: dict[str, dict[str, PrimitiveStats]] = {}
    for axis in AXES:
        stats[axis] = {}
        for p in PRIMITIVES[axis]:
            a = anchors[axis][p]
            ps = PrimitiveStats(
                mean=a["median"],
                std=max(_SIGMA_FLOOR, a["mad"]),
                n=_LARGE_N,
            )
            stats[axis][p] = ps

    return BaselineStats(self_stats=stats, universe_stats=stats)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _median(values: list[float]) -> float | None:
    """Return the median of a list, or None if empty."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _has_alert(records) -> bool:
    return any(r.alert_raised for r in records)


def _first_alert_idx(records) -> int | None:
    for r in records:
        if r.alert_raised:
            return r.bucket_end_ms   # bucket_end_ms == bucket index in synthetic mode
    return None


# ---------------------------------------------------------------------------
# PUBLIC: measure
# ---------------------------------------------------------------------------

def measure(
    cfg: DetectorConfig,
    anchors: dict,
    cov: dict,
    delta: float,
    n_streams: int,
    length: int,
    seed: int,
) -> dict:
    """Measure Type-I error, power, and median detection latency.

    Type-I: fraction of pure-Normal streams (theta_onset=0) with any alert_raised.
    Power:  fraction of Drifting streams (theta_onset=1 → onset@0) with any alert_raised.
    median_detection_latency_buckets: median over alerted Drifting streams of
        (first alert_raised bucket index - onset_idx).

    Seed per stream is (seed + i) for determinism.
    """
    baseline = _baseline_from_anchors(anchors)

    # ---- Type-I: pure-Normal streams ----
    type_i_alerts = 0
    for i in range(n_streams):
        spec = SynthSpec(
            anchors=anchors,
            cov=cov,
            delta=delta,
            theta_onset=0.0,          # pure Normal
            theta_persist=1.0,
            length=length,
            seed=seed + i,
        )
        stream, _ = generate_stream(spec)
        records = run_detector_on_stream(stream, baseline, cfg)
        if _has_alert(records):
            type_i_alerts += 1

    type_i = type_i_alerts / n_streams

    # ---- Power: onset-at-0 Drifting streams ----
    power_alerts = 0
    latencies: list[float] = []
    for i in range(n_streams):
        spec = SynthSpec(
            anchors=anchors,
            cov=cov,
            delta=delta,
            theta_onset=1.0,          # onset at bucket 0
            theta_persist=1.0,
            length=length,
            seed=seed + n_streams + i,   # offset to avoid reusing Type-I seeds
        )
        stream, onset_idx = generate_stream(spec)
        records = run_detector_on_stream(stream, baseline, cfg)
        first_idx = _first_alert_idx(records)
        if first_idx is not None:
            power_alerts += 1
            lat = first_idx - (onset_idx if onset_idx is not None else 0)
            latencies.append(lat)

    power = power_alerts / n_streams
    median_latency = _median(latencies)

    return {
        "type_i": type_i,
        "power": power,
        "median_detection_latency_buckets": median_latency,
    }


# ---------------------------------------------------------------------------
# PUBLIC: lda_weights  (Fisher LDA within one axis)
# ---------------------------------------------------------------------------

def lda_weights(
    axis: str,
    anchors: dict,
    cov: dict,
    delta: float,
    seed: int,
    n_samples: int = 200,
    ridge: float = 1e-3,
) -> dict[str, float]:
    """Fisher LDA weights separating Normal vs Drifting for one axis.

    Generates n_samples from each class using hmm_synth, extracts the
    axis-relevant primitives, computes within-class scatter (ridge-regularised),
    solves w = S_W^{-1} (mu_1 - mu_0), normalises sum|w|==1.

    Falls back to equal weights if S_W is singular / degenerate.
    """
    prims = list(PRIMITIVES[axis])
    k = len(prims)

    # --- Generate samples ---
    def _gen_samples(theta_onset: float, base_seed: int) -> list[list[float]]:
        samples = []
        for i in range(n_samples):
            spec = SynthSpec(
                anchors=anchors,
                cov=cov,
                delta=delta,
                theta_onset=theta_onset,
                theta_persist=1.0,
                length=1,   # single-bucket; we only want one emission
                seed=base_seed + i,
            )
            stream, _ = generate_stream(spec)
            row = stream[0]
            samples.append([row[p] for p in prims])
        return samples

    normal_samples = _gen_samples(0.0, seed)
    drift_samples  = _gen_samples(1.0, seed + n_samples)

    def _mean_vec(samples: list[list[float]]) -> list[float]:
        n = len(samples)
        return [sum(s[j] for s in samples) / n for j in range(k)]

    mu0 = _mean_vec(normal_samples)
    mu1 = _mean_vec(drift_samples)

    # --- Within-class scatter (sum of squared deviations, pooled) ---
    def _scatter(samples: list[list[float]], mu: list[float]) -> list[list[float]]:
        S = [[0.0] * k for _ in range(k)]
        for s in samples:
            d = [s[j] - mu[j] for j in range(k)]
            for i in range(k):
                for j in range(k):
                    S[i][j] += d[i] * d[j]
        return S

    S0 = _scatter(normal_samples, mu0)
    S1 = _scatter(drift_samples,  mu1)

    # pooled within-class scatter + ridge regularisation
    S_W = [[S0[i][j] + S1[i][j] for j in range(k)] for i in range(k)]
    total_n = len(normal_samples) + len(drift_samples)
    for i in range(k):
        S_W[i][i] += ridge * total_n   # ridge in same scale as summed scatter

    # --- Solve S_W @ w = (mu1 - mu0) via Gaussian elimination ---
    diff = [mu1[j] - mu0[j] for j in range(k)]

    w = _solve_linear(S_W, diff)

    # Fallback to equal weights if solution is None (degenerate)
    if w is None:
        w_eq = 1.0 / k
        return {p: w_eq for p in prims}

    # Normalise so sum|w| == 1
    total_abs = sum(abs(wi) for wi in w)
    if total_abs < _SIGMA_FLOOR:
        # All-zero solution: fallback
        w_eq = 1.0 / k
        return {p: w_eq for p in prims}

    return {prims[j]: w[j] / total_abs for j in range(k)}


def _solve_linear(A: list[list[float]], b: list[float]) -> list[float] | None:
    """Solve A @ x = b via Gaussian elimination with partial pivoting.

    Returns None if the system is singular / degenerate (pivot < eps).
    """
    n = len(b)
    # Augmented matrix [A | b]
    aug = [A[i][:] + [b[i]] for i in range(n)]

    eps = 1e-12
    for col in range(n):
        # Partial pivot
        max_row = max(range(col, n), key=lambda r: abs(aug[r][col]))
        aug[col], aug[max_row] = aug[max_row], aug[col]

        pivot = aug[col][col]
        if abs(pivot) < eps:
            return None  # singular

        for row in range(col + 1, n):
            factor = aug[row][col] / pivot
            for j in range(col, n + 1):
                aug[row][j] -= factor * aug[col][j]

    # Back-substitution
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = aug[i][n]
        for j in range(i + 1, n):
            x[i] -= aug[i][j] * x[j]
        if abs(aug[i][i]) < eps:
            return None
        x[i] /= aug[i][i]

    return x


# ---------------------------------------------------------------------------
# PUBLIC: grid_search
# ---------------------------------------------------------------------------

# Default grid axes (spec §15)
_DEFAULT_BUCKET_MS = (
    1 * 3600 * 1000,    # 1h
    4 * 3600 * 1000,    # 4h
    24 * 3600 * 1000,   # 24h
)
_DEFAULT_M         = (2, 3, 4, 6, 9, 12)
_DEFAULT_TAU       = (0.3, 1.0)
_DEFAULT_WEIGHTS   = ("equal", "lda")
_DEFAULT_KAPPA     = (7, 14, 30)

_MS_6H  = 6 * 3600 * 1000
_MS_7D  = 7 * 24 * 3600 * 1000


def _count_dof(tau, weights, kappa) -> int:
    """Count distinct tuned knobs as a simple integer for Occam tiebreak."""
    # tau (1 per-axis scalar treated as 1 knob),
    # weights choice (1 knob), kappa (1 knob) = 3 base knobs.
    # Always the same here; kept as a function for easy extension.
    return 3


def _build_cfg_for_row(
    bucket_ms: int,
    M: int,
    tau: float,
    weights_choice: str,
    kappa: float,
    anchors: dict,
    cov: dict,
    delta: float,
    lda_seed: int,
) -> DetectorConfig:
    """Build a DetectorConfig for one grid cell."""
    if weights_choice == "lda":
        w = {
            axis: lda_weights(axis, anchors, cov, delta, seed=lda_seed)
            for axis in AXES
        }
    else:  # "equal"
        w = {
            axis: {p: 1.0 / len(PRIMITIVES[axis]) for p in PRIMITIVES[axis]}
            for axis in AXES
        }

    return DetectorConfig(
        bucket_ms=bucket_ms,
        M=M,
        tau={a: tau for a in AXES},
        weights=w,
        kappa=kappa,
    )


def grid_search(
    anchors: dict,
    cov: dict,
    seed: int,
    n_streams: int,
    delta: float = 1.5,
    bucket_ms_options: tuple = _DEFAULT_BUCKET_MS,
    M_options: tuple = _DEFAULT_M,
    tau_options: tuple = _DEFAULT_TAU,
    weights_options: tuple = _DEFAULT_WEIGHTS,
    kappa_options: tuple = _DEFAULT_KAPPA,
) -> list[dict]:
    """Enumerate hyper-param combos, measure each, return list of result rows.

    Constraint: only includes rows where 6h <= M * bucket_ms <= 7d.

    Each row contains:
        bucket_ms, M, tau, weights, kappa,
        type_i, power, median_detection_latency_buckets, dof.
    """
    rows = []
    stream_seed = seed + 1_000_000  # separate namespace from lda seeds

    for bucket_ms in bucket_ms_options:
        for M in M_options:
            floor_ms = bucket_ms * M
            if floor_ms < _MS_6H or floor_ms > _MS_7D:
                continue   # constraint: 6h <= M*bucket <= 7d

            for tau in tau_options:
                for weights_choice in weights_options:
                    for kappa in kappa_options:
                        # Use a cell-specific seed for LDA to keep determinism
                        lda_seed = (
                            seed ^ hash((bucket_ms, M, tau, weights_choice, kappa)) & 0xFFFFFF
                        )
                        cfg = _build_cfg_for_row(
                            bucket_ms=bucket_ms,
                            M=M,
                            tau=tau,
                            weights_choice=weights_choice,
                            kappa=kappa,
                            anchors=anchors,
                            cov=cov,
                            delta=delta,
                            lda_seed=lda_seed,
                        )
                        # stream length: enough to observe M consecutive buckets past burn_in
                        length = max(200, cfg.burn_in + M * 5)

                        res = measure(
                            cfg=cfg,
                            anchors=anchors,
                            cov=cov,
                            delta=delta,
                            n_streams=n_streams,
                            length=length,
                            seed=stream_seed,
                        )
                        # advance stream_seed per cell for independence
                        stream_seed += n_streams * 2 + 1

                        rows.append({
                            "bucket_ms":      bucket_ms,
                            "M":              M,
                            "tau":            tau,
                            "weights":        weights_choice,
                            "kappa":          kappa,
                            "type_i":         res["type_i"],
                            "power":          res["power"],
                            "median_detection_latency_buckets": res["median_detection_latency_buckets"],
                            "dof":            _count_dof(tau, weights_choice, kappa),
                        })

    return rows


# ---------------------------------------------------------------------------
# PUBLIC: pick_winner
# ---------------------------------------------------------------------------

def pick_winner(rows: list[dict]) -> tuple[dict | None, bool]:
    """Select the best configuration from grid rows.

    Strict: power >= 0.70 AND type_i <= 0.02.
    Relaxed: power >= 0.70 AND type_i <= 0.05 (sets relaxed flag True).
    Ranking: power DESC, then M*bucket_ms ASC (shorter floor), then dof ASC.

    Returns (winner_or_None, typeI_target_relaxed_bool).
    """
    def _rank_key(row):
        return (
            -row["power"],
            row["bucket_ms"] * row["M"],
            row["dof"],
        )

    # Strict pass
    strict = [r for r in rows if r["power"] >= 0.70 and r["type_i"] <= 0.02]
    if strict:
        return min(strict, key=_rank_key), False

    # Relaxed pass
    relaxed = [r for r in rows if r["power"] >= 0.70 and r["type_i"] <= 0.05]
    if relaxed:
        return min(relaxed, key=_rank_key), True

    return None, True


# ---------------------------------------------------------------------------
# PUBLIC: run_calibration
# ---------------------------------------------------------------------------

def run_calibration(
    anchors: dict,
    cov: dict,
    seed: int,
    out_path: str,
    n_streams: int = 10_000,
    delta_power: float = 1.5,
    power_by_delta_deltas: tuple = (0.5, 1.0, 1.5),
    bucket_ms_options: tuple = _DEFAULT_BUCKET_MS,
    M_options: tuple = _DEFAULT_M,
    tau_options: tuple = _DEFAULT_TAU,
    weights_options: tuple = _DEFAULT_WEIGHTS,
    kappa_options: tuple = _DEFAULT_KAPPA,
) -> dict:
    """Run the full calibration pipeline and write a JSON artifact.

    Steps:
    1. grid_search over all combos with n_streams each.
    2. pick_winner to select the best configuration.
    3. Compute power_by_delta curve for the winner (or a default cfg).
    4. Write JSON artifact and return it.

    Artifact keys:
        grid_rows             — all grid search rows
        winning_tuple         — the winning hyper-param dict (or None)
        realized_type_i       — type_i of the winner
        realized_power        — power of the winner
        power_by_delta        — dict {str(delta): power} for winner cfg
        typeI_target_relaxed  — bool
    """
    rows = grid_search(
        anchors=anchors,
        cov=cov,
        seed=seed,
        n_streams=n_streams,
        delta=delta_power,
        bucket_ms_options=bucket_ms_options,
        M_options=M_options,
        tau_options=tau_options,
        weights_options=weights_options,
        kappa_options=kappa_options,
    )

    winner, relaxed = pick_winner(rows)

    if winner is not None:
        realized_type_i = winner["type_i"]
        realized_power  = winner["power"]
        winner_cfg = _build_cfg_for_row(
            bucket_ms=winner["bucket_ms"],
            M=winner["M"],
            tau=winner["tau"],
            weights_choice=winner["weights"],
            kappa=winner["kappa"],
            anchors=anchors,
            cov=cov,
            delta=delta_power,
            lda_seed=seed ^ 0xABCD,
        )
    else:
        realized_type_i = None
        realized_power  = None
        # fallback: a sensible default config for the delta curve
        winner_cfg = DetectorConfig(
            bucket_ms=4 * 3600 * 1000,
            M=6,
            tau={a: 0.3 for a in AXES},
            weights={
                a: {p: 1.0 / len(PRIMITIVES[a]) for p in PRIMITIVES[a]}
                for a in AXES
            },
            kappa=14,
        )

    # Power-by-delta curve on the winner config
    pbd_seed = seed + 2_000_000
    power_by_delta: dict[str, float] = {}
    for d in power_by_delta_deltas:
        length = max(200, winner_cfg.burn_in + winner_cfg.M * 5)
        res = measure(
            cfg=winner_cfg,
            anchors=anchors,
            cov=cov,
            delta=d,
            n_streams=max(20, n_streams // 20),   # cheaper sub-run for the curve
            length=length,
            seed=pbd_seed,
        )
        pbd_seed += 1_000
        power_by_delta[str(d)] = res["power"]

    artifact = {
        "grid_rows":            rows,
        "winning_tuple":        winner,
        "realized_type_i":      realized_type_i,
        "realized_power":       realized_power,
        "power_by_delta":       power_by_delta,
        "typeI_target_relaxed": relaxed,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)

    return artifact
