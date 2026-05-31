"""Tests for the equity-aware series runner.

The series runner mirrors detector.run_detector's per-bucket loop but consumes
a PRECOMPUTED series (each bucket already carries its 9 primitive values +
equity + end_ms). This is the equity-aware path the synthetic stream adapter
(run_detector_on_stream) lacks: it threads real equity through the guard band.
"""
from research.hyperliquid.detector.config import (
    PrimitiveStats, BaselineStats, DetectorConfig, PRIMITIVES, AXES,
)
from research.hyperliquid.experiments.series_runner import (
    run_detector_on_series, AlertRecord,
)

H = 3600 * 1000  # 1 hour in ms


def _baseline(mean=0.0, std=1.0):
    s = {a: {p: PrimitiveStats(mean, std, 10_000) for p in PRIMITIVES[a]} for a in AXES}
    u = {a: {p: PrimitiveStats(mean, std, 9_999) for p in PRIMITIVES[a]} for a in AXES}
    return BaselineStats(s, u)


def _leverage_cfg(M=3, burn_in=5, guard_x=0.70):
    """Config that focuses entirely on leverage (exposure axis, weight=1.0)."""
    return DetectorConfig(
        bucket_ms=H, M=M,
        tau={a: 0.3 for a in AXES},
        weights={a: {p: (1.0 if p == "leverage" else 0.0) for p in PRIMITIVES[a]}
                 for a in AXES},
        kappa=0, burn_in=burn_in, guard_x=guard_x,
    )


def _flat_prims(leverage=0.0):
    """All 9 primitives at 0 except leverage."""
    out = {}
    for a in AXES:
        for p in PRIMITIVES[a]:
            out[p] = leverage if p == "leverage" else 0.0
    return out


def _bucket(end_ms, leverage, equity):
    return {"prim": _flat_prims(leverage), "equity": equity, "end_ms": end_ms}


def test_drifting_series_raises_early_alert_before_first_liq():
    """Leverage ramps each bucket while equity stays healthy -> early exposure alert
    constructed to land before a first_liq set far in the future."""
    series = []
    for i in range(40):
        series.append(_bucket((i + 1) * H, leverage=2.0 * (i + 1), equity=100.0))

    cfg = _leverage_cfg(M=3, burn_in=5)
    first_liq_ms = 1000 * H  # liquidation far in the future

    recs = run_detector_on_series(series, _baseline(), cfg, first_liq_ms)

    early = [r for r in recs if r.alert_raised and r.is_early]
    assert early, "expected at least one early alert, got none"
    assert early[0].carrying_axis == "exposure"
    # the early alert must precede first_liq
    assert early[0].bucket_end_ms < first_liq_ms


def test_one_record_per_bucket():
    series = [_bucket((i + 1) * H, leverage=0.0, equity=100.0) for i in range(7)]
    cfg = _leverage_cfg()
    recs = run_detector_on_series(series, _baseline(), cfg, None)
    assert len(recs) == 7
    assert [r.bucket_end_ms for r in recs] == [(i + 1) * H for i in range(7)]


def test_no_drift_no_alert():
    series = [_bucket((i + 1) * H, leverage=0.0, equity=100.0) for i in range(30)]
    cfg = _leverage_cfg()
    recs = run_detector_on_series(series, _baseline(), cfg, None)
    assert not any(r.alert_raised for r in recs)


def test_alert_after_first_liq_is_not_early():
    """An alert that fires after first_liq_ms must have is_early=False."""
    series = []
    for i in range(40):
        series.append(_bucket((i + 1) * H, leverage=2.0 * (i + 1), equity=100.0))
    cfg = _leverage_cfg(M=3, burn_in=5)
    # first_liq at 1ms -> every bucket is at/after liquidation
    recs = run_detector_on_series(series, _baseline(), cfg, first_liq_ms=1)
    alerts = [r for r in recs if r.alert_raised]
    assert alerts, "should still raise an alert (just not early)"
    assert all(not r.is_early for r in alerts)


def test_unhealthy_equity_is_not_early():
    """Once equity drops below guard_x * running_peak, is_early must be False even
    if the composite fires."""
    series = []
    # ramp leverage hard; equity craters from bucket 10 onward
    for i in range(40):
        eq = 100.0 if i < 10 else 50.0  # 50 < 0.70*100 -> unhealthy
        series.append(_bucket((i + 1) * H, leverage=2.0 * (i + 1), equity=eq))
    cfg = _leverage_cfg(M=3, burn_in=5, guard_x=0.70)
    recs = run_detector_on_series(series, _baseline(), cfg, None)
    # any alert that fires in an unhealthy bucket (i>=10) must not be early
    for r in recs:
        if r.alert_raised and r.bucket_end_ms > 10 * H:
            assert r.is_early is False


def test_none_equity_buckets_are_not_early():
    """Buckets with equity=None (before first snapshot) must not claim 'early',
    and running_peak must be unchanged by them."""
    series = []
    # first two buckets have no equity snapshot
    series.append(_bucket(1 * H, leverage=2.0, equity=None))
    series.append(_bucket(2 * H, leverage=4.0, equity=None))
    for i in range(2, 40):
        series.append(_bucket((i + 1) * H, leverage=2.0 * (i + 1), equity=100.0))
    cfg = _leverage_cfg(M=3, burn_in=5)
    recs = run_detector_on_series(series, _baseline(), cfg, None)
    assert recs[0].is_early is False
    assert recs[1].is_early is False


def test_running_peak_tracks_only_non_none_equity():
    """running_peak is taken over non-None equity; a None bucket after a peak does
    not reset health. After peak=200, a 150-equity bucket (>=0.70*200=140) is still
    healthy and early."""
    series = [
        _bucket(1 * H, leverage=2.0, equity=200.0),   # peak=200
        _bucket(2 * H, leverage=4.0, equity=None),     # None -> peak unchanged
        _bucket(3 * H, leverage=6.0, equity=150.0),    # 150 >= 0.7*200=140 -> healthy
    ]
    cfg = _leverage_cfg(M=1, burn_in=0, guard_x=0.70)
    recs = run_detector_on_series(series, _baseline(), cfg, None)
    # bucket index 2 (end 3H): healthy relative to peak 200
    assert recs[2].is_early is True
    assert recs[1].is_early is False  # None equity
