"""End-to-end detector orchestration.

run_detector wires together:
  bucketize -> PrimitiveState -> axis_observations -> AxisSPRT
  -> Composite -> guard_band

and returns a list of AlertRecord — one per bucket.

Equity-None handling: a bucket with no equity snapshot (equity_end is None,
which only happens before the first snapshot) cannot be confirmed healthy, so
is_early=False and running_peak is left unchanged — we never claim "early" on
missing data.
"""
from __future__ import annotations
from dataclasses import dataclass

from research.hyperliquid.detector.bucketing import bucketize
from research.hyperliquid.detector.primitives import PrimitiveState
from research.hyperliquid.detector.axis import axis_observations
from research.hyperliquid.detector.sprt_axis import AxisSPRT
from research.hyperliquid.detector.composite import Composite
from research.hyperliquid.detector.guard_band import is_early
from research.hyperliquid.detector.config import AXES


@dataclass
class AlertRecord:
    bucket_end_ms: int
    fired: bool
    alert_raised: bool
    is_early: bool
    carrying_axis: str | None


def run_detector(
    traj,
    baseline,
    cfg,
    origin_ms: int,
    end_ms: int,
    coin_sigma: dict,
    pooled_sigma: float,
    first_liq_ms: int | None = None,
    orders=None,
) -> list[AlertRecord]:
    """Run the full drift-detector pipeline on a master's trajectory.

    Parameters
    ----------
    traj : Trajectory
        The master trader's trajectory (trades + equity + ledger).
    baseline : BaselineStats
        Frozen self+universe stats for shrinkage z-scoring.
    cfg : DetectorConfig
        All detector hyper-parameters.
    origin_ms : int
        Start of the detection window (ms).
    end_ms : int
        End of the detection window (ms, exclusive).
    coin_sigma : dict[str, float]
        Per-coin daily-return std for size_in_sigma normalisation.
    pooled_sigma : float
        Fallback std for coins not in coin_sigma.
    first_liq_ms : int | None
        Timestamp (ms) of the master's first liquidation event, or None.
    orders : list | None
        Optional trigger-order snapshots passed through to bucketize.

    Returns
    -------
    list[AlertRecord]
        One record per bucket, in chronological order.
    """
    buckets = bucketize(traj, origin_ms, end_ms, cfg.bucket_ms, orders=orders)

    pstate = PrimitiveState(coin_sigma, pooled_sigma)
    sprt = AxisSPRT(cfg)
    comp = Composite(cfg)

    running_peak = 0.0
    records: list[AlertRecord] = []

    for b in buckets:
        prim = pstate.bucket_values(b)
        obs = axis_observations(prim, baseline, cfg)
        p_by_axis = {a: sprt.update(a, obs[a]) for a in AXES}
        stepres = comp.step(p_by_axis)

        # None-equity (before the first snapshot): no data, so we cannot claim the
        # account is healthy — is_early=False and running_peak is left unchanged.
        if b.equity_end is not None:
            running_peak = max(running_peak, b.equity_end)
            early = is_early(b.equity_end, running_peak, b.end_ms, first_liq_ms, cfg.guard_x)
        else:
            early = False

        records.append(AlertRecord(
            bucket_end_ms=b.end_ms,
            fired=stepres.fired,
            alert_raised=stepres.alert_raised,
            is_early=early,
            carrying_axis=stepres.carrying_axis,
        ))

    return records


def run_detector_on_stream(
    stream,
    baseline,
    cfg,
    first_liq_idx: int | None = None,
) -> list[AlertRecord]:
    """Run the detector pipeline on a precomputed stream of 9-primitive dicts.

    This is the synthetic-calibration entry point: the stream already carries
    the per-bucket primitive values (e.g. from hmm_synth.generate_stream), so we
    skip bucketize / PrimitiveState entirely and feed each bucket straight into
    axis_observations -> AxisSPRT -> Composite.  The bucket *index* is the time
    coordinate (used as AlertRecord.bucket_end_ms).

    Guard band: synthetic streams model no equity curve, so there is no
    equity-health check.  Lead-time in the power suite is measured back to the
    HMM onset, not to a liquidation.  We therefore treat every bucket as being
    in the early-warning zone (is_early=True) unless a liquidation index is
    supplied, in which case is_early is True strictly before first_liq_idx and
    False at/after it.  This mirrors guard_band.is_early's pre-first-liquidation
    clause without the (absent) equity term.

    Parameters
    ----------
    stream : list[dict[str, float]]
        Per-bucket dicts of the 9 primitive values in natural units.
    baseline : BaselineStats
        Frozen self+universe stats for shrinkage z-scoring; must be aligned with
        the stream's anchors for the z-scores to be meaningful.
    cfg : DetectorConfig
        Detector hyper-parameters.
    first_liq_idx : int | None
        Bucket index of a modeled liquidation, or None (no liquidation modeled).

    Returns
    -------
    list[AlertRecord]
        One record per bucket; bucket_end_ms == bucket index.
    """
    sprt = AxisSPRT(cfg)
    comp = Composite(cfg)

    records: list[AlertRecord] = []
    for idx, prim in enumerate(stream):
        obs = axis_observations(prim, baseline, cfg)
        p_by_axis = {a: sprt.update(a, obs[a]) for a in AXES}
        stepres = comp.step(p_by_axis)

        early = first_liq_idx is None or idx < first_liq_idx

        records.append(AlertRecord(
            bucket_end_ms=idx,
            fired=stepres.fired,
            alert_raised=stepres.alert_raised,
            is_early=early,
            carrying_axis=stepres.carrying_axis,
        ))

    return records
