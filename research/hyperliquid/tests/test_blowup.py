from research.hyperliquid.models import EquityPoint, Trade
from research.hyperliquid.blowup import forward_only_blowup_time

H = 86_400_000  # 1 day in ms


def eq(seq):
    return [EquityPoint(int(t * H), float(v)) for t, v in seq]


def test_clean_blowup_labels_at_threshold_cross():
    curve = eq([(0, 100), (1, 120), (2, 55), (3, 0)])   # peak 120; t=2 dd 54% (> 50%)
    t = forward_only_blowup_time(curve, [], dd_pct=0.5,
                                 recovery_frac=0.8, recovery_horizon_ms=H)
    assert t == int(2 * H)


def test_transient_dip_with_recovery_is_not_a_blowup():
    curve = eq([(0, 100), (1, 50), (2, 95), (3, 110)])
    t = forward_only_blowup_time(curve, [], dd_pct=0.5,
                                 recovery_frac=0.8, recovery_horizon_ms=2 * H)
    assert t is None


def test_liquidation_fill_takes_precedence_if_earlier():
    curve = eq([(0, 100), (5, 80)])
    liq = [Trade(time=int(1 * H), coin="BTC", direction="Close Long", px=1, sz=1,
                 closed_pnl=-99, start_position=1, is_liquidation=True)]
    t = forward_only_blowup_time(curve, liq, dd_pct=0.5,
                                 recovery_frac=0.8, recovery_horizon_ms=H)
    assert t == int(1 * H)


def test_no_look_ahead_truncating_future_does_not_change_label():
    base = eq([(0, 100), (1, 120), (2, 55)])   # t=2 dd 54% (> 50%)
    future_a = base + eq([(3, 0)])
    future_b = base + eq([(3, 0), (10, 999999)])  # wild future spike beyond horizon
    t_a = forward_only_blowup_time(future_a, [], 0.5, 0.8, H)
    t_b = forward_only_blowup_time(future_b, [], 0.5, 0.8, H)
    assert t_a == t_b == int(2 * H)


def test_recovery_within_horizon_blocks_label_but_outside_does_not():
    within = eq([(0, 100), (1, 120), (2, 55), (2.5, 100)])   # recover +0.5d (<= H)
    beyond = eq([(0, 100), (1, 120), (2, 55), (4, 100)])     # recover +2d  (>  H)
    assert forward_only_blowup_time(within, [], 0.5, 0.8, H) is None
    assert forward_only_blowup_time(beyond, [], 0.5, 0.8, H) == int(2 * H)
