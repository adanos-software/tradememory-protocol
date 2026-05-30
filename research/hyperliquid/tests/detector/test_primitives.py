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


def test_size_in_sigma_uses_largest_fills_coin_in_multicoin_bucket():
    # largest fill is ETH(sz=10, sigma=5); last fill is BTC(sz=1, sigma=1).
    # must normalise by ETH's sigma -> 10/5 = 2.0, not the last coin's -> 10/1 = 10.
    traj = mk_traj(trades=[mk_trade(2, coin="ETH", direction="Open Long", px=10, sz=10),
                           mk_trade(6, coin="BTC", direction="Open Long", px=100, sz=1)],
                   equity=mk_eq([(0, 1000), (H, 1000)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={"ETH": 5.0, "BTC": 1.0}, pooled_sigma=1.0)
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


# ---------------------------------------------------------------------------
# Task 5 — Discipline axis
# ---------------------------------------------------------------------------

def test_stop_attach_rate_counts_opening_fills_with_live_trigger():
    traj = mk_traj(trades=[mk_trade(5, coin="BTC", direction="Open Long", px=100, sz=1)],
                   equity=mk_eq([(0, 100), (H, 100)]))
    buckets = bucketize(traj, 0, H, H, orders=[{"coin": "BTC", "ts": 4, "is_trigger": True}])
    st = PrimitiveState(coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["stop_attach_rate"] == 1.0


def test_stop_attach_rate_zero_when_no_trigger_order():
    traj = mk_traj(trades=[mk_trade(5, coin="BTC", direction="Open Long", px=100, sz=1)],
                   equity=mk_eq([(0, 100), (H, 100)]))
    buckets = bucketize(traj, 0, H, H, orders=[{"coin": "BTC", "ts": 4, "is_trigger": False}])
    st = PrimitiveState(coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["stop_attach_rate"] == 0.0


def test_reduce_only_rate_detects_position_shrink():
    traj = mk_traj(trades=[mk_trade(2, direction="Open Long", px=100, sz=2),
                           mk_trade(6, direction="Close Long", px=100, sz=1)],
                   equity=mk_eq([(0, 100), (H, 100)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["reduce_only_rate"] == 0.5


def test_mean_hold_hours_closed_position():
    # Open at t=0, close at t=2H → hold = 2h
    traj = mk_traj(trades=[mk_trade(0, direction="Open Long", px=100, sz=1),
                           mk_trade(2 * H, direction="Close Long", px=100, sz=1)],
                   equity=mk_eq([(0, 100), (4 * H, 100)]))
    buckets = bucketize(traj, 0, 4 * H, 4 * H)
    st = PrimitiveState(coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["mean_hold_hours"] == 2.0


def test_order_events_normalize():
    from research.hyperliquid.normalize import order_events
    raw = [
        {"coin": "BTC", "timestamp": 1000, "isTrigger": True, "isPositionTpsl": False},
        {"coin": "ETH", "timestamp": 2000, "isTrigger": False, "isPositionTpsl": True},
        {"coin": "SOL", "timestamp": 3000, "isTrigger": False, "isPositionTpsl": False},
    ]
    evs = order_events(raw)
    assert evs[0] == {"coin": "BTC", "ts": 1000, "is_trigger": True}
    assert evs[1] == {"coin": "ETH", "ts": 2000, "is_trigger": True}
    assert evs[2] == {"coin": "SOL", "ts": 3000, "is_trigger": False}


def test_bucketize_with_orders_assigns_to_bucket():
    traj = mk_traj(trades=[mk_trade(5, coin="BTC", direction="Open Long", px=100, sz=1)],
                   equity=mk_eq([(0, 100), (H, 100), (2 * H, 100)]))
    orders = [{"coin": "BTC", "ts": 5, "is_trigger": True}]
    buckets = bucketize(traj, 0, 2 * H, H, orders=orders)
    # order at ts=5 is in [0, H) → bucket 0
    assert any(o["is_trigger"] for o in buckets[0].orders)
    assert buckets[1].orders == []


# ---------------------------------------------------------------------------
# Task 6 — Tilt axis
# ---------------------------------------------------------------------------

def test_topup_count_from_deposit_ledger():
    from research.hyperliquid.models import LedgerEvent
    traj = mk_traj(equity=mk_eq([(0, 100), (H, 100)]),
                   ledger=[LedgerEvent(5, "deposit", 500.0),
                           LedgerEvent(6, "withdraw", 100.0)])
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["topup_count"] == 1


def test_topup_count_multiple_deposits():
    from research.hyperliquid.models import LedgerEvent
    traj = mk_traj(equity=mk_eq([(0, 100), (H, 100)]),
                   ledger=[LedgerEvent(1, "deposit", 100.0),
                           LedgerEvent(2, "deposit", 200.0),
                           LedgerEvent(3, "funding", 5.0)])
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["topup_count"] == 2


def test_loser_add_counts_adding_into_losing_position():
    traj = mk_traj(trades=[mk_trade(2, direction="Open Long", px=100, sz=1),
                           mk_trade(6, direction="Open Long", px=90, sz=1)],
                   equity=mk_eq([(0, 100), (H, 80)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["loser_add_count"] == 1


def test_loser_add_zero_when_adding_into_winning_position():
    # Long at 100, then add at 110 (winning) → loser_add should be 0
    traj = mk_traj(trades=[mk_trade(2, direction="Open Long", px=100, sz=1),
                           mk_trade(6, direction="Open Long", px=110, sz=1)],
                   equity=mk_eq([(0, 100), (H, 120)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["loser_add_count"] == 0


def test_loser_add_counts_short_side_adding_into_loss():
    # Open Short at 100, then add Short at 110 (price moved up against the short = loss) -> loser_add
    traj = mk_traj(trades=[mk_trade(2, direction="Open Short", px=100, sz=1),
                           mk_trade(6, direction="Open Short", px=110, sz=1)],
                   equity=mk_eq([(0, 100), (H, 80)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["loser_add_count"] == 1


def test_fill_rate_spike_zero_when_no_history():
    # First bucket: no trailing history → 0
    traj = mk_traj(trades=[mk_trade(5, direction="Open Long", px=100, sz=1)],
                   equity=mk_eq([(0, 100), (H, 100)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["fill_rate_spike"] == 0.0


def test_fill_rate_spike_ratio_over_trailing_mean():
    # Bucket 0: 1 fill → stored in history
    # Bucket 1: 4 fills → spike = 4 / 1 = 4.0
    traj = mk_traj(
        trades=[mk_trade(5, direction="Open Long", px=100, sz=1),
                mk_trade(H + 1, direction="Open Long", px=100, sz=1),
                mk_trade(H + 2, direction="Open Long", px=100, sz=1),
                mk_trade(H + 3, direction="Open Long", px=100, sz=1),
                mk_trade(H + 4, direction="Open Long", px=100, sz=1)],
        equity=mk_eq([(0, 100), (H, 100), (2 * H, 100)]),
    )
    buckets = bucketize(traj, 0, 2 * H, H)
    st = PrimitiveState(coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    st.bucket_values(buckets[0])
    vals = st.bucket_values(buckets[1])
    assert vals["fill_rate_spike"] == 4.0
