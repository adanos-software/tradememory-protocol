"""Equity-aware detector loop over a PRECOMPUTED bucket series.

``run_detector_on_series`` mirrors ``detector.run_detector``'s per-bucket loop,
but instead of building buckets/primitives from a raw Trajectory it consumes a
series whose buckets already carry their 9 primitive values, equity, and end_ms.

This is the equity-aware path the synthetic stream adapter
(``detector.run_detector_on_stream``) lacks: the synthetic adapter has no equity
curve and treats every bucket as early, whereas the real-cohort experiments need
the guard band threaded with real per-bucket equity (and its None-before-first-
snapshot semantics, copied verbatim from ``detector.run_detector``).

Per-bucket pipeline (identical to detector.run_detector, minus bucketize/
PrimitiveState which are already done):

    axis_observations(b["prim"], baseline, cfg)
      -> AxisSPRT.update per axis
      -> Composite.step
      -> is_early(b["equity"], running_peak, b["end_ms"], first_liq_ms, guard_x)

Running-peak / None-equity rule (same as detector.run_detector):
  - track running_peak over non-None equity only;
  - a None-equity bucket cannot be confirmed healthy => is_early=False and
    running_peak is left unchanged.

State objects (AxisSPRT, Composite) are created exactly once per call.

Imports: stdlib + research.hyperliquid.* only. No numpy, no tradememory.owm.*.
"""
from __future__ import annotations

from dataclasses import dataclass

from research.hyperliquid.detector.axis import axis_observations
from research.hyperliquid.detector.sprt_axis import AxisSPRT
from research.hyperliquid.detector.composite import Composite
from research.hyperliquid.detector.guard_band import is_early
from research.hyperliquid.detector.config import AXES

__all__ = ["AlertRecord", "run_detector_on_series"]


@dataclass
class AlertRecord:
    bucket_end_ms: int
    fired: bool
    alert_raised: bool
    is_early: bool
    carrying_axis: str | None


def run_detector_on_series(
    series: list[dict],
    baseline,
    cfg,
    first_liq_ms: int | None,
) -> list[AlertRecord]:
    """Run the drift detector over a precomputed bucket series.

    Parameters
    ----------
    series : list[dict]
        Chronologically ordered buckets. Each bucket is a dict with:
          - "prim":   dict[str, float] of the 9 primitive values (natural units)
          - "equity": float | None     (None before the first equity snapshot)
          - "end_ms": int              (bucket close timestamp, ms)
    baseline : BaselineStats
        Frozen self+universe stats used for James-Stein shrinkage z-scoring.
    cfg : DetectorConfig
        All detector hyper-parameters (weights, kappa, M, alpha, guard_x, ...).
    first_liq_ms : int | None
        Timestamp (ms) of the master's first liquidation, or None if none.

    Returns
    -------
    list[AlertRecord]
        One record per bucket, in input order. Each record carries
        (bucket_end_ms, fired, alert_raised, is_early, carrying_axis).
    """
    sprt = AxisSPRT(cfg)
    comp = Composite(cfg)

    running_peak = 0.0
    records: list[AlertRecord] = []

    for b in series:
        obs = axis_observations(b["prim"], baseline, cfg)
        p_by_axis = {a: sprt.update(a, obs[a]) for a in AXES}
        stepres = comp.step(p_by_axis)

        equity = b["equity"]
        # None-equity (before the first snapshot): cannot confirm health, so
        # is_early=False and running_peak is left unchanged (mirrors detector.py).
        if equity is not None:
            running_peak = max(running_peak, equity)
            early = is_early(equity, running_peak, b["end_ms"], first_liq_ms, cfg.guard_x)
        else:
            early = False

        records.append(AlertRecord(
            bucket_end_ms=b["end_ms"],
            fired=stepres.fired,
            alert_raised=stepres.alert_raised,
            is_early=early,
            carrying_axis=stepres.carrying_axis,
        ))

    return records
