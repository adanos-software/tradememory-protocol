from __future__ import annotations
from research.hyperliquid.detector.primitives import PrimitiveState
from research.hyperliquid.detector.bucketing import bucketize
from research.hyperliquid.tests.detector.helpers import mk_trade, mk_eq, mk_traj

H = 3600 * 1000


# ---------------------------------------------------------------------------
# Task 4 — Exposure axis
# ---------------------------------------------------------------------------

def test_leverage_uses_notional_over_equity():
    traj = mk_traj(trades=[mk_trade(5, coin="BTC", direction="Open Long", px=100, sz=2,
                                    start_position=0)],
                   equity=mk_eq([(0, 100), (H, 100)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["leverage"] == 2.0


def test_leverage_carry_forward_when_empty():
    traj = mk_traj(trades=[mk_trade(5, px=100, sz=2)],
                   equity=mk_eq([(0, 100), (H, 100), (2 * H, 100)]))
    buckets = bucketize(traj, 0, 2 * H, H)
    st = PrimitiveState(coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    st.bucket_values(buckets[0])
    vals1 = st.bucket_values(buckets[1])
    assert vals1["leverage"] == 2.0


def test_size_in_sigma_scales_by_coin_vol():
    traj = mk_traj(trades=[mk_trade(5, coin="ETH", px=10, sz=4)],
                   equity=mk_eq([(0, 100), (H, 100)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={"ETH": 2.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["size_in_sigma"] == 2.0


def test_dict_shape_has_all_9_keys():
    traj = mk_traj(equity=mk_eq([(0, 100), (H, 100)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    expected = {
        "leverage", "notional_growth", "size_in_sigma",
        "stop_attach_rate", "reduce_only_rate", "mean_hold_hours",
        "topup_count", "loser_add_count", "fill_rate_spike",
    }
    assert set(vals.keys()) == expected


def test_notional_growth_non_empty_bucket():
    # pos goes from 0 -> 2*100 = 200 notional; growth = (200-0)/100 = 2.0
    traj = mk_traj(trades=[mk_trade(5, direction="Open Long", px=100, sz=2)],
                   equity=mk_eq([(0, 100), (H, 100)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["notional_growth"] == 2.0
