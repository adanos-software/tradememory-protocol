"""Tests for run_detector: end-to-end orchestration.

Verifies that the full pipeline (bucketize -> PrimitiveState -> axis_observations
-> AxisSPRT -> Composite -> guard_band) produces AlertRecord streams correctly.
"""
from research.hyperliquid.detector.config import (
    PrimitiveStats, BaselineStats, DetectorConfig, PRIMITIVES, AXES,
)
from research.hyperliquid.detector.detector import run_detector, run_detector_on_stream
from research.hyperliquid.tests.detector.helpers import (
    mk_trade, mk_eq, mk_traj, anchors_flat, identity_cov,
)

H = 3600 * 1000  # 1 hour in ms


def _baseline():
    s = {a: {p: PrimitiveStats(0.0, 1.0, 10_000) for p in PRIMITIVES[a]} for a in AXES}
    u = {a: {p: PrimitiveStats(0.0, 1.0, 9_999) for p in PRIMITIVES[a]} for a in AXES}
    return BaselineStats(s, u)


def _leverage_cfg(M=3, burn_in=5):
    """Config that focuses entirely on leverage (exposure axis, weight=1.0)."""
    return DetectorConfig(
        bucket_ms=H, M=M,
        tau={a: 0.3 for a in AXES},
        weights={a: {p: (1.0 if p == "leverage" else 0.0) for p in PRIMITIVES[a]}
                 for a in AXES},
        kappa=0,
        burn_in=burn_in,
    )


def test_drifting_master_raises_early_alert():
    """Leverage ramps each bucket while equity stays healthy → early exposure alert.

    Each bucket: one Open Long BTC sz=2, so position grows monotonically.
    Equity is flat at 100.0 → leverage = 2*(i+1) per bucket.
    baseline mean=0, std=1 → z = leverage → signed obs = -leverage → strongly negative.
    After burn_in (5) + M (3) buckets the composite must fire an early alert.
    """
    trades, eqpts = [], [(0, 100.0)]
    for i in range(40):
        trades.append(mk_trade(i * H + 5, coin="BTC", direction="Open Long",
                               px=100, sz=2))
        eqpts.append(((i + 1) * H, 100.0))   # equity flat & healthy

    traj = mk_traj(trades=trades, equity=mk_eq(eqpts))
    cfg = _leverage_cfg(M=3, burn_in=5)

    recs = run_detector(
        traj, _baseline(), cfg,
        origin_ms=0, end_ms=40 * H,
        coin_sigma={"BTC": 1.0}, pooled_sigma=1.0,
        first_liq_ms=None,
    )

    early = [r for r in recs if r.alert_raised and r.is_early]
    assert early, "expected at least one early alert, got none"
    assert early[0].carrying_axis == "exposure", (
        f"expected exposure to carry the alert, got {early[0].carrying_axis}"
    )


def test_returns_one_record_per_bucket():
    """run_detector returns exactly one AlertRecord per bucket."""
    trades = [mk_trade(H // 2, coin="BTC", direction="Open Long", px=100, sz=1)]
    eqpts = [(0, 100.0), (H, 100.0)]
    traj = mk_traj(trades=trades, equity=mk_eq(eqpts))
    cfg = _leverage_cfg()

    recs = run_detector(traj, _baseline(), cfg,
                        origin_ms=0, end_ms=3 * H,
                        coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    assert len(recs) == 3


def test_no_trades_no_alert():
    """A flat equity trajectory with no trades should never fire an alert."""
    eqpts = [(i * H, 100.0) for i in range(20)]
    traj = mk_traj(trades=[], equity=mk_eq(eqpts))
    cfg = _leverage_cfg()

    recs = run_detector(traj, _baseline(), cfg,
                        origin_ms=0, end_ms=20 * H,
                        coin_sigma={}, pooled_sigma=1.0)
    assert not any(r.alert_raised for r in recs)


def test_alert_after_first_liq_is_not_early():
    """An alert that fires after first_liq_ms should have is_early=False."""
    trades, eqpts = [], [(0, 100.0)]
    for i in range(40):
        trades.append(mk_trade(i * H + 5, coin="BTC", direction="Open Long",
                               px=100, sz=2))
        eqpts.append(((i + 1) * H, 100.0))

    traj = mk_traj(trades=trades, equity=mk_eq(eqpts))
    cfg = _leverage_cfg(M=3, burn_in=5)

    # first_liq_ms = 1ms into the timeline — all buckets are "after" liquidation
    recs = run_detector(
        traj, _baseline(), cfg,
        origin_ms=0, end_ms=40 * H,
        coin_sigma={"BTC": 1.0}, pooled_sigma=1.0,
        first_liq_ms=1,
    )

    alerts = [r for r in recs if r.alert_raised]
    assert alerts, "should still raise an alert (just not early)"
    assert all(not r.is_early for r in alerts), (
        "all alerts after first_liq_ms=1 must have is_early=False"
    )


def test_none_equity_buckets_are_not_early():
    """Buckets before the first equity snapshot (equity_end=None) must not claim 'early'."""
    # equity only appears at t=2.5H -> buckets 0 and 1 have equity_end=None
    trades = [mk_trade(H // 2, coin="BTC", direction="Open Long", px=100, sz=1)]
    eqpts = [(int(2.5 * H), 100.0)]
    traj = mk_traj(trades=trades, equity=mk_eq(eqpts))
    cfg = _leverage_cfg()

    recs = run_detector(traj, _baseline(), cfg,
                        origin_ms=0, end_ms=5 * H,
                        coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    assert len(recs) == 5  # no crash
    assert recs[0].is_early is False  # None equity -> not early
    assert recs[1].is_early is False


# ---------------------------------------------------------------------------
# run_detector_on_stream: synthetic-stream adapter (Task 13)
# ---------------------------------------------------------------------------
def _stream_baseline():
    """Baseline matching the synthetic anchors (median=0, mad=1 => std=1)."""
    s = {a: {p: PrimitiveStats(0.0, 1.0, 10_000) for p in PRIMITIVES[a]} for a in AXES}
    u = {a: {p: PrimitiveStats(0.0, 1.0, 9_999) for p in PRIMITIVES[a]} for a in AXES}
    return BaselineStats(s, u)


def _stream_cfg(M=3, burn_in=10):
    return DetectorConfig(
        bucket_ms=1, M=M,
        tau={a: 0.3 for a in AXES},
        weights={a: {p: 1 / 3 for p in PRIMITIVES[a]} for a in AXES},
        kappa=0, burn_in=burn_in,
    )


def test_run_on_stream_alerts_on_drift_after_onset():
    from research.hyperliquid.detector.hmm_synth import SynthSpec, generate_stream
    s = {a: {p: PrimitiveStats(0.0, 1.0, 10_000) for p in PRIMITIVES[a]} for a in AXES}
    u = {a: {p: PrimitiveStats(0.0, 1.0, 9999) for p in PRIMITIVES[a]} for a in AXES}
    base = BaselineStats(s, u)
    spec = SynthSpec(anchors=anchors_flat(), cov=identity_cov(),
                     delta=2.0, theta_onset=1.0, theta_persist=1.0, length=200, seed=3)
    stream, onset = generate_stream(spec)
    cfg = DetectorConfig(bucket_ms=1, M=3, tau={a: 0.3 for a in AXES},
                         weights={a: {p: 1 / 3 for p in PRIMITIVES[a]} for a in AXES},
                         kappa=0, burn_in=10)
    recs = run_detector_on_stream(stream, base, cfg)
    assert any(r.alert_raised for r in recs)


def test_run_on_stream_one_record_per_bucket():
    from research.hyperliquid.detector.hmm_synth import SynthSpec, generate_stream
    spec = SynthSpec(anchors=anchors_flat(), cov=identity_cov(),
                     delta=2.0, theta_onset=1.0, theta_persist=1.0, length=120, seed=4)
    stream, _ = generate_stream(spec)
    recs = run_detector_on_stream(stream, _stream_baseline(), _stream_cfg())
    assert len(recs) == 120
    # bucket index is used as the timestamp surrogate
    assert [r.bucket_end_ms for r in recs] == list(range(120))


def test_run_on_stream_pure_normal_no_alert():
    """A pure-Normal stream (no drift) must not raise an alert."""
    from research.hyperliquid.detector.hmm_synth import SynthSpec, generate_stream
    spec = SynthSpec(anchors=anchors_flat(), cov=identity_cov(),
                     delta=2.0, theta_onset=0.0, theta_persist=0.9, length=300, seed=5)
    stream, onset = generate_stream(spec)
    assert onset is None
    recs = run_detector_on_stream(stream, _stream_baseline(), _stream_cfg())
    assert not any(r.alert_raised for r in recs)


def test_run_on_stream_is_early_true_when_no_liq_idx():
    """With first_liq_idx=None, every bucket is in the early-warning band."""
    from research.hyperliquid.detector.hmm_synth import SynthSpec, generate_stream
    spec = SynthSpec(anchors=anchors_flat(), cov=identity_cov(),
                     delta=2.0, theta_onset=1.0, theta_persist=1.0, length=80, seed=6)
    stream, _ = generate_stream(spec)
    recs = run_detector_on_stream(stream, _stream_baseline(), _stream_cfg(),
                                  first_liq_idx=None)
    assert all(r.is_early for r in recs)


def test_run_on_stream_is_early_respects_first_liq_idx():
    """is_early is True strictly before first_liq_idx, False at/after it."""
    from research.hyperliquid.detector.hmm_synth import SynthSpec, generate_stream
    spec = SynthSpec(anchors=anchors_flat(), cov=identity_cov(),
                     delta=2.0, theta_onset=1.0, theta_persist=1.0, length=80, seed=7)
    stream, _ = generate_stream(spec)
    recs = run_detector_on_stream(stream, _stream_baseline(), _stream_cfg(),
                                  first_liq_idx=50)
    assert all(r.is_early for r in recs[:50])
    assert all(not r.is_early for r in recs[50:])


def test_run_on_stream_alert_index_precedes_onset_window():
    """Drift onset at 0 with delta=2 -> alert fires within the stream (lead-time ok)."""
    from research.hyperliquid.detector.hmm_synth import SynthSpec, generate_stream
    spec = SynthSpec(anchors=anchors_flat(), cov=identity_cov(),
                     delta=2.0, theta_onset=1.0, theta_persist=1.0, length=200, seed=8)
    stream, onset = generate_stream(spec)
    recs = run_detector_on_stream(stream, _stream_baseline(), _stream_cfg())
    fired = [r for r in recs if r.alert_raised]
    assert fired
    # an early alert should be flagged is_early when no liquidation is modeled
    assert fired[0].is_early
