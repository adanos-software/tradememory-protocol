"""Discipline-only ablation harness (Task 16).

Public API
----------
discipline_only_cfg(cfg)
    Return a copy of cfg with mask_axes=frozenset({"exposure","tilt"}) so only
    the discipline axis can carry the composite alert.

ablation_sanity(anchors, cov, cfg, seed, n_streams, length)
    Run 3 drift-axis scenarios (A/B/C) on both the full detector and the
    discipline-only detector, measuring detection latency per stream.
    Returns a dict with per-scenario stats.  Scenario A includes an
    event-clustered bootstrap CI (B=2000, 95%) of the median latency under
    the discipline-only detector.

Imports: stdlib + research.hyperliquid.* only.  No numpy.  Deterministic.
"""
from __future__ import annotations

import dataclasses
import random

from research.hyperliquid.detector.config import AXES, PRIMITIVES
from research.hyperliquid.detector.hmm_synth import SynthSpec, generate_stream
from research.hyperliquid.detector.detector import run_detector_on_stream
from research.hyperliquid.detector.calibration import _baseline_from_anchors


# ---------------------------------------------------------------------------
# Public: discipline_only_cfg
# ---------------------------------------------------------------------------

def discipline_only_cfg(cfg):
    """Return a copy of cfg with mask_axes=frozenset({"exposure","tilt"}).

    Only the discipline axis can carry the composite alert — the other two
    axes are permanently pinned at p=1.0 and cannot contribute evidence.

    Uses dataclasses.replace so all other fields are preserved unchanged.
    """
    return dataclasses.replace(cfg, mask_axes=frozenset({"exposure", "tilt"}))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _first_alert_idx(records) -> int | None:
    """Return the bucket_end_ms (== bucket index) of the first alert, or None."""
    for r in records:
        if r.alert_raised:
            return r.bucket_end_ms
    return None


def _run_scenario(
    anchors: dict,
    cov: dict,
    cfg,
    disc_cfg,
    drift_axes: frozenset,
    seed: int,
    n_streams: int,
    length: int,
    baseline,
) -> dict:
    """Generate n_streams Drifting streams with the given drift_axes and collect
    detection latencies for both the full and discipline-only detector.

    Returns a dict with:
        full_latencies      : list[int]   (streams where full detector alerted)
        disc_latencies      : list[int]   (streams where discipline-only alerted)
        full_power          : float
        disc_power          : float
    """
    full_latencies: list[int] = []
    disc_latencies: list[int] = []

    for i in range(n_streams):
        spec = SynthSpec(
            anchors=anchors,
            cov=cov,
            delta=2.0,        # strong drift for reliable detection in small n_streams
            theta_onset=1.0,  # onset at bucket 0 for well-defined latency
            theta_persist=1.0,
            length=length,
            seed=seed + i,
            drift_axes=drift_axes,
        )
        stream, onset_idx = generate_stream(spec)
        # onset_idx is always 0 when theta_onset=1.0
        onset = onset_idx if onset_idx is not None else 0

        # Full detector
        full_records = run_detector_on_stream(stream, baseline, cfg)
        full_first = _first_alert_idx(full_records)
        if full_first is not None:
            full_latencies.append(full_first - onset)

        # Discipline-only detector
        disc_records = run_detector_on_stream(stream, baseline, disc_cfg)
        disc_first = _first_alert_idx(disc_records)
        if disc_first is not None:
            disc_latencies.append(disc_first - onset)

    full_power = len(full_latencies) / n_streams
    disc_power = len(disc_latencies) / n_streams

    return {
        "full_latencies": full_latencies,
        "disc_latencies": disc_latencies,
        "full_power": full_power,
        "disc_power": disc_power,
    }


def _median(values: list) -> float | None:
    """Median of a list; None if empty."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 == 1 else (s[mid - 1] + s[mid]) / 2.0


def _bootstrap_ci_median(
    values: list[int],
    rng: random.Random,
    B: int = 2000,
    ci: float = 0.95,
) -> tuple[float, float]:
    """Event-clustered bootstrap CI of the median latency.

    Resamples len(values) latencies with replacement from `values` using
    the provided seeded rng (deterministic).  Returns (ci_low, ci_high) as
    the [alpha/2, 1-alpha/2] percentile of the B bootstrap medians.

    The "event-clustered" interpretation: each element of `values` is the
    outcome of one independent stream; resampling streams gives the correct
    cluster-resampling CI for the median.
    """
    n = len(values)
    if n == 0:
        return (float("nan"), float("nan"))

    boot_medians: list[float] = []
    for _ in range(B):
        resample = [rng.choice(values) for _ in range(n)]
        m = _median(resample)
        if m is not None:
            boot_medians.append(m)

    boot_medians.sort()
    alpha = 1.0 - ci
    lo_idx = int(alpha / 2.0 * len(boot_medians))
    hi_idx = int((1.0 - alpha / 2.0) * len(boot_medians)) - 1
    lo_idx = max(0, lo_idx)
    hi_idx = min(len(boot_medians) - 1, hi_idx)

    return (boot_medians[lo_idx], boot_medians[hi_idx])


# ---------------------------------------------------------------------------
# Public: ablation_sanity
# ---------------------------------------------------------------------------

def ablation_sanity(
    anchors: dict,
    cov: dict,
    cfg,
    seed: int,
    n_streams: int,
    length: int,
) -> dict:
    """Run 3 drift-axis scenarios on full and discipline-only detectors.

    Scenario A: drift_axes={"discipline"}            — discipline-only drift
    Scenario B: drift_axes={"exposure","discipline","tilt"} — full drift
    Scenario C: drift_axes={"exposure","tilt"}       — exposure+tilt only

    For each scenario, n_streams Drifting streams are generated (theta_onset=1.0,
    delta=2.0 for reliable power) and run through both detectors.  Detection
    latency = first alert bucket index - onset_idx.

    Scenario A additionally includes an event-clustered bootstrap CI (B=2000,
    95%) of the discipline-only detector's median latency.

    Sanity bar: scenario_A["ci_low"] > 0 confirms the discipline-only detector
    can demonstrably detect discipline-only drift (CI excludes 0).

    Parameters
    ----------
    anchors : dict
        Per-axis/primitive anchor stats (median + mad).
    cov : dict
        9x9 correlation matrix keyed by primitive name.
    cfg : DetectorConfig
        Full detector config (no mask_axes).
    seed : int
        Seed for stream generation and bootstrap RNG.
    n_streams : int
        Number of synthetic streams per scenario.
    length : int
        Number of buckets per stream.

    Returns
    -------
    dict with keys "scenario_A", "scenario_B", "scenario_C", each containing:
        full_power, disc_power, full_median_latency, disc_median_latency
    scenario_A also contains:
        ci_low, ci_high, median, disc_to_full_latency_ratio
    """
    baseline = _baseline_from_anchors(anchors)
    disc_cfg = discipline_only_cfg(cfg)

    scenarios = {
        "A": frozenset({"discipline"}),
        "B": frozenset({"exposure", "discipline", "tilt"}),
        "C": frozenset({"exposure", "tilt"}),
    }

    results = {}
    for label, drift_axes in scenarios.items():
        # Each scenario gets a distinct seed offset to avoid stream reuse
        scenario_seed = seed + 10_000 * (ord(label) - ord("A"))
        data = _run_scenario(
            anchors=anchors,
            cov=cov,
            cfg=cfg,
            disc_cfg=disc_cfg,
            drift_axes=drift_axes,
            seed=scenario_seed,
            n_streams=n_streams,
            length=length,
            baseline=baseline,
        )

        full_med = _median(data["full_latencies"])
        disc_med = _median(data["disc_latencies"])

        row: dict = {
            "full_power": data["full_power"],
            "disc_power": data["disc_power"],
            "full_median_latency": full_med,
            "disc_median_latency": disc_med,
        }

        if label == "A":
            # Event-clustered bootstrap CI on discipline-only latencies
            boot_rng = random.Random(seed + 99_999)
            ci_low, ci_high = _bootstrap_ci_median(
                data["disc_latencies"],
                rng=boot_rng,
                B=2000,
                ci=0.95,
            )
            row["ci_low"] = ci_low
            row["ci_high"] = ci_high
            row["median"] = disc_med
            # Ratio: discipline-only latency / full-detector latency (both on scenario A)
            if full_med is not None and full_med != 0:
                row["disc_to_full_latency_ratio"] = (
                    disc_med / full_med if disc_med is not None else None
                )
            else:
                row["disc_to_full_latency_ratio"] = None

        results[f"scenario_{label}"] = row

    return results
