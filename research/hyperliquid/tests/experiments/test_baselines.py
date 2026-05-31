"""Tests for the non-trivial early baselines B0/B1/B2/B3.

Each baseline returns the first alert bucket_end_ms under the SAME guard band
(is_early True at that bucket), else None. B0 is the too-late reference (first
bucket below guard_x equity, NOT guard-banded).
"""
from research.hyperliquid.detector.config import PRIMITIVES, AXES
from research.hyperliquid.experiments.baselines import (
    b0_too_late,
    b1_leverage_percentile,
    b2_drawdown_velocity,
    b3_leverage_up_and_add,
    _percentile,
)

H = 3600 * 1000
GUARD_X = 0.70


def _prims(leverage=0.0, loser_add_count=0.0):
    out = {}
    for a in AXES:
        for p in PRIMITIVES[a]:
            out[p] = 0.0
    out["leverage"] = leverage
    out["loser_add_count"] = loser_add_count
    return out


def _bucket(end_ms, equity, leverage=0.0, loser_add_count=0.0):
    return {
        "prim": _prims(leverage, loser_add_count),
        "equity": equity,
        "end_ms": end_ms,
    }


# ---------------------------------------------------------------------------
# _percentile helper
# ---------------------------------------------------------------------------
def test_percentile_basic():
    vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    # linear-interpolation p90 of 1..10
    assert abs(_percentile(vals, 0.90) - 9.1) < 1e-9


def test_percentile_constant():
    assert _percentile([5, 5, 5, 5], 0.90) == 5


def test_percentile_single():
    assert _percentile([42.0], 0.90) == 42.0


# ---------------------------------------------------------------------------
# B1: leverage percentile
# ---------------------------------------------------------------------------
def test_b1_fires_when_leverage_exceeds_early_p90():
    series = []
    # first third (buckets 0..9): leverage flat at 3.0 -> p90 = 3.0
    for i in range(10):
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=3.0))
    # rest: stays at 3 until a clear spike at bucket 15 (> 3.0), equity healthy
    for i in range(10, 30):
        lev = 20.0 if i == 15 else 3.0
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=lev))

    out = b1_leverage_percentile(series, first_liq_ms=None, guard_x=GUARD_X)
    assert out == 16 * H  # bucket index 15 -> end_ms = 16*H


def test_b1_no_fire_when_leverage_stays_below_p90():
    series = [_bucket((i + 1) * H, equity=100.0, leverage=2.0) for i in range(30)]
    # constant leverage -> p90 = 2.0, never strictly exceeded
    assert b1_leverage_percentile(series, None, GUARD_X) is None


def test_b1_skips_unhealthy_buckets():
    """A leverage spike in an UNHEALTHY bucket (below guard band) must not fire B1."""
    series = []
    for i in range(10):
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=3.0))  # flat early window
    # spike at bucket 12 but equity crashed -> not guard-banded -> no early fire
    for i in range(10, 30):
        eq = 50.0 if i >= 11 else 100.0  # 50 < 0.7*100 unhealthy from bucket 11
        lev = 20.0 if i == 12 else 3.0
        series.append(_bucket((i + 1) * H, equity=eq, leverage=lev))
    assert b1_leverage_percentile(series, None, GUARD_X) is None


def test_b1_respects_first_liq():
    series = []
    for i in range(10):
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=3.0))  # flat early window
    for i in range(10, 30):
        lev = 20.0 if i == 15 else 3.0
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=lev))
    # liquidation at 12*H -> the spike at 16*H is after liq -> not early -> None
    assert b1_leverage_percentile(series, first_liq_ms=12 * H, guard_x=GUARD_X) is None


# ---------------------------------------------------------------------------
# B2: drawdown velocity
# ---------------------------------------------------------------------------
def test_b2_fires_on_dd_acceleration():
    """Equity holds flat (zero DD velocity) for the early window, then a sharp
    healthy-but-accelerating drawdown spikes velocity -> fire."""
    series = []
    # early window: tiny equity wiggles -> small DD velocity
    eqs_early = [100, 100, 99, 100, 100, 99, 100, 100, 99, 100]
    for i, eq in enumerate(eqs_early):
        series.append(_bucket((i + 1) * H, equity=float(eq)))
    # later: a quick but still-healthy drop from 100 -> 80 (>=0.7*100) at bucket 15
    eqs_late = [100, 100, 100, 100, 100, 80, 100, 100, 100, 100,
                100, 100, 100, 100, 100, 100, 100, 100, 100, 100]
    for i, eq in enumerate(eqs_late):
        series.append(_bucket((10 + i + 1) * H, equity=float(eq)))

    out = b2_drawdown_velocity(series, first_liq_ms=None, guard_x=GUARD_X)
    assert out == 16 * H  # the 100->80 drop happens at bucket index 15


def test_b2_no_fire_on_steady_state():
    series = [_bucket((i + 1) * H, equity=100.0) for i in range(30)]
    assert b2_drawdown_velocity(series, None, GUARD_X) is None


def test_b2_acceleration_not_level():
    """A deep but STEADY drawdown (high level, zero velocity after the step) must
    not keep firing once velocity returns to early-window levels."""
    series = []
    # early window flat
    for i in range(10):
        series.append(_bucket((i + 1) * H, equity=100.0))
    # step down once to 80 then hold -> velocity spikes once at the step only
    for i in range(10, 30):
        eq = 100.0 if i < 12 else 80.0
        series.append(_bucket((i + 1) * H, equity=eq))
    out = b2_drawdown_velocity(series, None, GUARD_X)
    # fires at the step (bucket 12 -> end 13*H), the first acceleration
    assert out == 13 * H


# ---------------------------------------------------------------------------
# B3: leverage-up AND loser-add
# ---------------------------------------------------------------------------
def test_b3_fires_on_lever_up_and_add():
    series = []
    for i in range(20):
        # leverage rises at bucket 10 with a loser add
        lev = 5.0 if i < 10 else (5.0 if i != 10 else 8.0)
        add = 1.0 if i == 10 else 0.0
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=lev, loser_add_count=add))
    out = b3_leverage_up_and_add(series, first_liq_ms=None, guard_x=GUARD_X)
    assert out == 11 * H  # bucket index 10


def test_b3_no_fire_without_add():
    series = []
    for i in range(20):
        lev = float(5 + i)  # leverage rising every bucket
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=lev, loser_add_count=0.0))
    # leverage up but never a loser add -> None
    assert b3_leverage_up_and_add(series, None, GUARD_X) is None


def test_b3_no_fire_add_without_lever_up():
    series = []
    for i in range(20):
        lev = 5.0  # flat leverage
        add = 1.0 if i == 8 else 0.0
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=lev, loser_add_count=add))
    # adds happen but leverage never increases -> None
    assert b3_leverage_up_and_add(series, None, GUARD_X) is None


def test_b3_respects_guard_band():
    series = []
    for i in range(20):
        eq = 100.0 if i < 10 else 50.0  # unhealthy from bucket 10
        lev = 5.0 if i != 10 else 8.0
        add = 1.0 if i == 10 else 0.0
        series.append(_bucket((i + 1) * H, equity=eq, leverage=lev, loser_add_count=add))
    # the lever-up+add at bucket 10 is in an unhealthy bucket -> not early -> None
    assert b3_leverage_up_and_add(series, None, GUARD_X) is None


# ---------------------------------------------------------------------------
# B0: too-late reference
# ---------------------------------------------------------------------------
def test_b0_fires_at_first_unhealthy_bucket():
    series = []
    for i in range(20):
        eq = 100.0 if i < 12 else 60.0  # 60 < 0.7*100 -> unhealthy at bucket 12
        series.append(_bucket((i + 1) * H, equity=eq))
    out = b0_too_late(series, guard_x=GUARD_X)
    assert out == 13 * H  # bucket index 12 -> end 13*H


def test_b0_none_when_always_healthy():
    series = [_bucket((i + 1) * H, equity=100.0) for i in range(20)]
    assert b0_too_late(series, GUARD_X) is None
