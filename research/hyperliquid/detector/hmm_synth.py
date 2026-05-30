"""Label-blind 2-state HMM synthetic master generator (pure-Python, no numpy).

Generates a stream of per-bucket dicts of the 9 behavioral-primitive values in
*natural units* (z-scoring happens downstream in axis.py).  Two latent states:

  Normal    — every primitive emitted around its anchor median.
  Drifting  — every primitive's mean shifted by  delta * mad  in the BAD_DIR of
              its axis (exposure/tilt up, discipline down).

Emissions are multivariate Gaussian with
    cov_ij = corr_ij * sigma_i * sigma_j ,   sigma_i = 1.4826 * mad_i
(robust std from MAD), sampled as  x = mean + L @ z  where  L = cholesky(cov)
and z are i.i.d. standard normals (Box-Muller).

"Label-blind": the generator never inspects detector internals or labels — it
only consumes anchors / correlation / delta and the BAD_DIR sign table.  The
detector sees only the natural-unit stream, so there is no information leak
between the data-generating process and the method under test.

Transition model
----------------
theta_onset controls when (if ever) the chain enters Drifting:

  theta_onset == 0.0   pure Normal forever                  -> onset_idx = None
                       (Type-I / false-positive suite)
  theta_onset == 1.0   Drifting from bucket 0               -> onset_idx = 0
  0 < theta_onset < 1  exactly ONE onset bucket, drawn once from the seeded rng,
                       then Drifting is absorbing (stay Drifting to the end).

Rationale for the absorbing single-onset choice (power suite): the calibration
measures lead-time from the alert back to a single, well-defined onset.  A chain
that flickers Normal<->Drifting would have an ill-defined "onset", so once the
master starts drifting we keep it drifting.  ``theta_persist`` is part of the
spec/dataclass (self-transition probability of the Drifting state) but is held
at its absorbing limit here; it is retained so the same SynthSpec can later drive
a flicker model without an API change.

Pure-Python numerics implemented below: _cholesky, _box_muller, _mvn_sample,
_psd_project.  Imports are restricted to stdlib + random + the detector config
(satisfies the AST import-isolation guard: no numpy/scipy, no tradememory.owm).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from research.hyperliquid.detector.config import AXES, PRIMITIVES, BAD_DIR

# MAD -> robust std multiplier (consistency factor for the normal distribution).
MAD_TO_STD = 1.4826

# Canonical primitive order (axis-major); the covariance matrix rows/cols and the
# mean vector all follow this order.
PRIM_ORDER: tuple[str, ...] = tuple(p for a in AXES for p in PRIMITIVES[a])

# primitive -> its axis (for the BAD_DIR drift sign lookup).
_AXIS_OF: dict[str, str] = {p: a for a in AXES for p in PRIMITIVES[a]}


@dataclass
class SynthSpec:
    """Specification for one synthetic master stream.

    Parameters
    ----------
    anchors : dict[str, dict[str, dict]]
        anchors[axis][primitive] = {"median": m, "mad": d} — per-primitive
        location (median) and scale (MAD) in natural units.
    cov : dict[str, dict[str, float]]
        9x9 cross-primitive CORRELATION matrix keyed by primitive name
        (cov[pi][pj]); identity = independent primitives.
    delta : float
        Drift magnitude in MAD units (mean shift = delta * mad in the bad dir).
    theta_onset : float
        Onset control (see module docstring): 0.0 pure-Normal, 1.0 onset@0,
        0<.<1 single absorbing onset drawn from the seeded rng.
    theta_persist : float
        Drifting self-transition probability (held at the absorbing limit here;
        retained for forward-compat — see module docstring).
    length : int
        Number of buckets to emit.
    seed : int
        Seed for the local random.Random — determinism, no global rng.
    """

    anchors: dict
    cov: dict
    delta: float
    theta_onset: float
    theta_persist: float
    length: int
    seed: int


# ---------------------------------------------------------------------------
# pure-Python numerics
# ---------------------------------------------------------------------------
def _cholesky(matrix: list[list[float]]) -> list[list[float]]:
    """Cholesky-Banachiewicz factorisation: return lower-triangular L, A = L L^T.

    Standard two-loop textbook algorithm.  Raises ValueError if the matrix is
    not positive-definite (a non-positive radicand on the diagonal) — the caller
    is expected to _psd_project first if repair is needed.
    """
    n = len(matrix)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                diag = matrix[i][i] - s
                if diag <= 0.0:
                    raise ValueError(
                        f"matrix not positive-definite at index {i} "
                        f"(radicand {diag!r} <= 0)"
                    )
                L[i][j] = math.sqrt(diag)
            else:
                L[i][j] = (matrix[i][j] - s) / L[j][j]
    return L


def _psd_project(matrix: list[list[float]]) -> list[list[float]]:
    """Repair a near-PSD matrix so _cholesky succeeds.

    Symmetrise (average with the transpose), then add eps*I with eps escalating
    (1e-9, 1e-8, ... up to 1e0) until Cholesky succeeds.  Simple jitter — adequate
    for the well-behaved correlation matrices used in this calibration.
    """
    n = len(matrix)
    # symmetrise
    sym = [[0.5 * (matrix[i][j] + matrix[j][i]) for j in range(n)] for i in range(n)]

    eps = 1e-9
    while eps <= 1.0:
        jittered = [row[:] for row in sym]
        for i in range(n):
            jittered[i][i] += eps
        try:
            _cholesky(jittered)
            return jittered
        except ValueError:
            eps *= 10.0
    raise ValueError(
        "_psd_project failed: matrix not repairable to PSD with diagonal jitter "
        "up to eps=1.0 (input is far from a valid correlation matrix)"
    )


def _box_muller(rng, n: int) -> list[float]:
    """Return n standard normals from a random.Random via the Box-Muller transform.

    Each uniform pair (u1, u2) yields two independent N(0,1) draws; for odd n the
    final spare draw is discarded.  u1 is floored away from 0 to avoid log(0).
    """
    out: list[float] = []
    while len(out) < n:
        u1 = rng.random()
        u2 = rng.random()
        if u1 < 1e-300:  # guard log(0); astronomically rare but deterministic-safe
            u1 = 1e-300
        r = math.sqrt(-2.0 * math.log(u1))
        theta = 2.0 * math.pi * u2
        out.append(r * math.cos(theta))
        if len(out) < n:
            out.append(r * math.sin(theta))
    return out


def _mvn_sample(mean: list[float], L: list[list[float]], rng) -> list[float]:
    """Sample one multivariate normal: x = mean + L @ z, z ~ N(0, I).

    L is the lower-triangular Cholesky factor of the covariance matrix.
    """
    n = len(mean)
    z = _box_muller(rng, n)
    out = [0.0] * n
    for i in range(n):
        acc = 0.0
        # L is lower-triangular: only k <= i contribute
        for k in range(i + 1):
            acc += L[i][k] * z[k]
        out[i] = mean[i] + acc
    return out


# ---------------------------------------------------------------------------
# covariance / mean assembly
# ---------------------------------------------------------------------------
def _sigmas(spec: SynthSpec) -> list[float]:
    """Robust std per primitive (canonical order): sigma_i = 1.4826 * mad_i."""
    sig = []
    for p in PRIM_ORDER:
        axis = _AXIS_OF[p]
        mad = spec.anchors[axis][p]["mad"]
        sig.append(MAD_TO_STD * mad)
    return sig


def _covariance(spec: SynthSpec, sig: list[float]) -> list[list[float]]:
    """Assemble cov_ij = corr_ij * sigma_i * sigma_j in canonical primitive order."""
    n = len(PRIM_ORDER)
    cov = [[0.0] * n for _ in range(n)]
    for i, pi in enumerate(PRIM_ORDER):
        for j, pj in enumerate(PRIM_ORDER):
            corr = spec.cov[pi][pj]
            cov[i][j] = corr * sig[i] * sig[j]
    return cov


def _mean_vector(spec: SynthSpec, drifting: bool) -> list[float]:
    """Mean per primitive (canonical order).

    Normal:    mean_i = median_i
    Drifting:  mean_i = median_i + delta * mad_i * BAD_DIR[axis_of(i)]
    """
    mean = []
    for p in PRIM_ORDER:
        axis = _AXIS_OF[p]
        a = spec.anchors[axis][p]
        m = a["median"]
        if drifting:
            m += spec.delta * a["mad"] * BAD_DIR[axis]
        mean.append(m)
    return mean


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def _pick_onset(spec: SynthSpec, rng) -> int | None:
    """Resolve the onset bucket index from theta_onset (see module docstring)."""
    # 0.0 and 1.0 are exact sentinels — the calibration grid passes them as
    # literals. Any intermediate value takes the single-absorbing-onset path.
    if spec.theta_onset == 0.0:
        return None
    if spec.theta_onset == 1.0:
        return 0
    # 0 < theta_onset < 1: single absorbing onset, drawn once from the seeded rng.
    if spec.length <= 0:
        return None
    return rng.randrange(spec.length)


def generate_stream(spec: SynthSpec) -> tuple[list[dict[str, float]], int | None]:
    """Generate a synthetic master stream from a SynthSpec.

    Returns
    -------
    (stream, onset_idx)
        stream    : list[dict[str, float]] — length == spec.length, each a dict
                    of the 9 primitive values (natural units) for that bucket.
        onset_idx : int | None — bucket index where Drifting begins; None for a
                    pure-Normal stream.
    """
    rng = random.Random(spec.seed)

    onset_idx = _pick_onset(spec, rng)

    sig = _sigmas(spec)
    cov = _covariance(spec, sig)
    L = _cholesky(_psd_project(cov))

    mean_normal = _mean_vector(spec, drifting=False)
    mean_drift = _mean_vector(spec, drifting=True)

    stream: list[dict[str, float]] = []
    for t in range(spec.length):
        drifting = onset_idx is not None and t >= onset_idx
        mean = mean_drift if drifting else mean_normal
        x = _mvn_sample(mean, L, rng)
        stream.append({PRIM_ORDER[i]: x[i] for i in range(len(PRIM_ORDER))})

    return stream, onset_idx
