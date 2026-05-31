"""Tests for the early-window baseline builder (stability guard + std-scale)."""
import math

from research.hyperliquid.detector.config import (
    PrimitiveStats, PRIMITIVES, AXES,
)
from research.hyperliquid.experiments.early_baseline import (
    build_early_window_baseline,
)

H = 3600 * 1000


def _universe_stats(mean=0.0, std=1.0, n=500):
    return {a: {p: PrimitiveStats(mean, std, n) for p in PRIMITIVES[a]} for a in AXES}


def _cfg():
    from research.hyperliquid.detector.config import DetectorConfig
    return DetectorConfig(
        bucket_ms=H, M=3,
        tau={a: 0.3 for a in AXES},
        weights={a: {p: 1 / 3 for p in PRIMITIVES[a]} for a in AXES},
        kappa=14,
    )


def _flat_prims(leverage=0.0):
    out = {}
    for a in AXES:
        for p in PRIMITIVES[a]:
            out[p] = leverage if p == "leverage" else 0.0
    return out


def _bucket(end_ms, equity, leverage=0.0):
    return {"prim": _flat_prims(leverage), "equity": equity, "end_ms": end_ms}


def test_healthy_then_drifting_yields_prefix_baseline():
    """A series that is healthy for the first 20 buckets then craters should yield a
    baseline built from the healthy prefix only, and be included."""
    series = []
    # healthy prefix: equity flat at 100, leverage stable ~ small
    for i in range(20):
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=2.0))
    # drift: equity craters, leverage explodes
    for i in range(20, 40):
        series.append(_bucket((i + 1) * H, equity=40.0, leverage=20.0))

    baseline, info = build_early_window_baseline(
        series, _universe_stats(), _cfg(),
        healthy_frac=0.90, min_healthy_buckets=10,
    )
    assert info["excluded"] is False
    assert baseline is not None
    # leverage self-mean should reflect the healthy prefix (~2.0), not the drift (20)
    lev = baseline.self_stats["exposure"]["leverage"]
    assert abs(lev.mean - 2.0) < 1e-6
    # universe passed through unchanged
    assert baseline.universe_stats["exposure"]["leverage"].n == 500


def test_always_drifting_series_is_excluded():
    """An always-drifting series (equity monotonically falling from bucket 0) has no
    sustained healthy segment >= min_healthy_buckets -> excluded (stability guard)."""
    series = []
    eq = 100.0
    for i in range(40):
        eq *= 0.85  # falls every bucket -> never recovers to peak
        series.append(_bucket((i + 1) * H, equity=eq, leverage=5.0 + i))

    baseline, info = build_early_window_baseline(
        series, _universe_stats(), _cfg(),
        healthy_frac=0.90, min_healthy_buckets=10,
    )
    assert info["excluded"] is True
    assert baseline is None
    assert "reason" in info


def test_too_short_healthy_segment_is_excluded():
    """Healthy prefix shorter than min_healthy_buckets -> excluded."""
    series = []
    for i in range(5):
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=2.0))
    for i in range(5, 40):
        series.append(_bucket((i + 1) * H, equity=30.0, leverage=20.0))

    baseline, info = build_early_window_baseline(
        series, _universe_stats(), _cfg(),
        healthy_frac=0.90, min_healthy_buckets=10,
    )
    assert info["excluded"] is True
    assert baseline is None


def test_std_scale_floor_for_constant_primitive():
    """A primitive that is constant in the healthy segment must get the std-based
    scale floor: max(std=0, 0.05*(1+|median|), 1e-3), never 0."""
    series = []
    for i in range(20):
        # leverage constant at 4.0 -> std=0 -> scale = 0.05*(1+4) = 0.25
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=4.0))

    baseline, info = build_early_window_baseline(
        series, _universe_stats(), _cfg(),
        healthy_frac=0.90, min_healthy_buckets=10,
    )
    assert info["excluded"] is False
    lev = baseline.self_stats["exposure"]["leverage"]
    assert lev.mean == 4.0
    assert lev.std == max(0.0, 0.05 * (1 + 4.0), 1e-3)
    assert lev.std > 0


def test_none_equity_buckets_skipped_for_health_but_prims_unavailable():
    """Buckets with equity=None can't be confirmed healthy; the healthy segment is
    formed from buckets that ARE confirmed healthy. A leading None block doesn't
    crash and doesn't poison the running peak."""
    series = []
    series.append(_bucket(1 * H, equity=None, leverage=99.0))   # None: skipped
    for i in range(1, 21):
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=3.0))
    baseline, info = build_early_window_baseline(
        series, _universe_stats(), _cfg(),
        healthy_frac=0.90, min_healthy_buckets=10,
    )
    assert info["excluded"] is False
    lev = baseline.self_stats["exposure"]["leverage"]
    # the None bucket's leverage=99 must NOT contaminate the baseline
    assert abs(lev.mean - 3.0) < 1e-6


def test_info_reports_healthy_segment_length():
    # 30 all-healthy buckets; default max_early_frac=0.5 caps the segment at
    # ceil(30*0.5)=15, so n_healthy reflects the early-window cap, not the whole life.
    series = [_bucket((i + 1) * H, equity=100.0, leverage=2.0) for i in range(30)]
    baseline, info = build_early_window_baseline(
        series, _universe_stats(), _cfg(),
        healthy_frac=0.90, min_healthy_buckets=10,
    )
    assert info["excluded"] is False
    assert info["n_healthy"] == 15  # early-fraction cap = ceil(30*0.5)


def test_early_fraction_cap_can_be_relaxed():
    """Raising max_early_frac to 1.0 lets the whole all-healthy series be used."""
    series = [_bucket((i + 1) * H, equity=100.0, leverage=2.0) for i in range(15)]
    baseline, info = build_early_window_baseline(
        series, _universe_stats(), _cfg(),
        healthy_frac=0.90, min_healthy_buckets=10, max_early_frac=1.0,
    )
    assert info["excluded"] is False
    assert info["n_healthy"] == 15


def test_std_based_scale_uses_real_std_when_large():
    """When the healthy-segment std exceeds both floors, it is used directly."""
    series = []
    levs = [1.0, 5.0, 9.0, 1.0, 5.0, 9.0, 1.0, 5.0, 9.0, 1.0, 5.0, 9.0]
    for i, lv in enumerate(levs):
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=lv))
    baseline, info = build_early_window_baseline(
        series, _universe_stats(), _cfg(),
        healthy_frac=0.90, min_healthy_buckets=10, max_early_frac=1.0,
    )
    lev = baseline.self_stats["exposure"]["leverage"]
    # population std of the leverage values
    vals = levs
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    std = math.sqrt(var)
    median = sorted(vals)[len(vals) // 2] if len(vals) % 2 == 1 else (
        (sorted(vals)[len(vals) // 2 - 1] + sorted(vals)[len(vals) // 2]) / 2.0)
    expected = max(std, 0.05 * (1 + abs(median)), 1e-3)
    assert abs(lev.std - expected) < 1e-9
