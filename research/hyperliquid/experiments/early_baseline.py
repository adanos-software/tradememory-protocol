"""Early-window self-baseline builder with stability guard.

``build_early_window_baseline`` constructs a master's *self* baseline from the
EARLIEST HEALTHY SEGMENT of its series, so that the detector z-scores later
behavior against the master's own pre-drift normal. Masters that are already
drifting at the start of the observation window have no such segment and are
EXCLUDED (the stability guard — they would otherwise calibrate "normal" to an
already-pathological state, leaking the label and defeating early detection).

Healthy-segment definition (documented choice)
----------------------------------------------
Walk the series from the start, tracking the running peak over confirmed
(non-None) equity. A bucket is "healthy" iff ``equity >= healthy_frac *
running_peak``. The healthy segment is the CONTIGUOUS HEALTHY PREFIX: it ends at
the first confirmed bucket whose equity drops below the threshold (the first
sustained drop), OR at a fixed early-fraction cap, whichever comes first.

The early-fraction cap (``max_early_frac``, default 0.5) ensures the baseline is
genuinely *early*-window: even a master who never draws down contributes at most
the first half of its series, never its whole life. (For the typical
healthy-then-drifting blowup the drop-below clause fires first and the cap is
irrelevant; the cap only bites for never-drawdown masters.)

None-equity buckets cannot be confirmed healthy, so they are skipped for the
health test and do not advance the running peak (same rule as detector.py).
Their ``prim`` values are therefore NOT aggregated into the baseline.

self_stats (documented choice)
------------------------------
For each primitive, over the healthy segment's ``prim`` values:
    mean  = median  (robust to the occasional outlier bucket)
    std   = max(population_std, 0.05 * (1 + |median|), 1e-3)
The std floor is the sparse-primitive fix: count/rate primitives are often
constant (std==0) over a short healthy window, which would make the downstream
z-score explode; the floor keeps the scale finite and proportionate.

universe_stats is passed in unchanged (cross-sectional, built by the controller
from the tuning split) and threaded straight into the returned BaselineStats.

Imports: stdlib + research.hyperliquid.* only. No numpy, no tradememory.owm.*.
"""
from __future__ import annotations

import math

from research.hyperliquid.detector.config import (
    AXES, PRIMITIVES, PrimitiveStats, BaselineStats,
)

__all__ = ["build_early_window_baseline"]


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _pop_std(values: list[float], mean: float) -> float:
    """Population standard deviation about `mean` (0.0 for a single value)."""
    n = len(values)
    if n <= 1:
        return 0.0
    var = sum((v - mean) ** 2 for v in values) / n
    return math.sqrt(var)


def _scale(std: float, median: float) -> float:
    """std-based scale with the sparse-primitive floor."""
    return max(std, 0.05 * (1.0 + abs(median)), 1e-3)


def build_early_window_baseline(
    series: list[dict],
    universe_stats: dict,
    cfg,
    healthy_frac: float = 0.90,
    min_healthy_buckets: int = 10,
    max_early_frac: float = 0.5,
):
    """Build the early-window self-baseline (or exclude an already-drifting master).

    Parameters
    ----------
    series : list[dict]
        Chronologically ordered buckets, each with "prim" (dict of 9 primitive
        values), "equity" (float | None), and "end_ms" (int).
    universe_stats : dict
        Cross-sectional stats[axis][primitive] = PrimitiveStats, passed through
        unchanged into the returned BaselineStats.
    cfg : DetectorConfig
        Carried for signature symmetry / future use; not currently read (the
        baseline is config-independent). Accepted so callers can pass it
        uniformly.
    healthy_frac : float
        A bucket is healthy iff equity >= healthy_frac * running_peak.
    min_healthy_buckets : int
        Minimum healthy-segment length; below this the master is excluded.
    max_early_frac : float
        Cap on the healthy segment as a fraction of the full series length
        (documented above): ensures the baseline stays early-window.

    Returns
    -------
    (BaselineStats | None, dict)
        On success: (BaselineStats(self_stats, universe_stats),
                     {"excluded": False, "n_healthy": int}).
        On exclusion: (None,
                     {"excluded": True, "reason": str, "n_healthy": int}).
    """
    # Early-fraction cap on how far into the series the healthy segment may run.
    cap = max(min_healthy_buckets, int(math.ceil(len(series) * max_early_frac)))

    healthy: list[dict] = []  # the buckets forming the healthy prefix
    running_peak = 0.0

    for idx, b in enumerate(series):
        if idx >= cap:
            break  # early-fraction cap reached; stop extending the segment
        equity = b["equity"]
        if equity is None:
            # cannot confirm health; skip for peak + health (do not break the
            # prefix on missing data — a leading None block is just unobserved)
            continue
        running_peak = max(running_peak, equity)
        if running_peak <= 0:
            # non-positive peak: cannot define health; treat as a drop (drifting)
            break
        if equity >= healthy_frac * running_peak:
            healthy.append(b)
        else:
            break  # first sustained drop below threshold ends the healthy prefix

    n_healthy = len(healthy)
    if n_healthy < min_healthy_buckets:
        return None, {
            "excluded": True,
            "reason": (
                f"healthy segment too short: {n_healthy} < "
                f"min_healthy_buckets={min_healthy_buckets} "
                f"(stability guard: master appears already drifting)"
            ),
            "n_healthy": n_healthy,
        }

    # Aggregate per-primitive self stats over the healthy segment.
    self_stats: dict[str, dict[str, PrimitiveStats]] = {}
    for axis in AXES:
        self_stats[axis] = {}
        for p in PRIMITIVES[axis]:
            vals = [b["prim"][p] for b in healthy]
            med = _median(vals)
            std = _pop_std(vals, sum(vals) / len(vals))
            self_stats[axis][p] = PrimitiveStats(
                mean=med,
                std=_scale(std, med),
                n=n_healthy,
            )

    baseline = BaselineStats(self_stats=self_stats, universe_stats=universe_stats)
    return baseline, {"excluded": False, "n_healthy": n_healthy}
