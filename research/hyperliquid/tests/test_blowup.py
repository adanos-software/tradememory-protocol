from research.hyperliquid.models import EquityPoint, Trade
from research.hyperliquid.blowup import (
    forward_only_blowup_time,
    forward_only_loss_confirmed_blowup,
)

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


# ---- loss-confirmed labeler (pre-reg #6, Option B) --------------------------

def pnl(seq):
    return [(int(t * H), float(v)) for t, v in seq]


def test_loss_confirmed_crater_labels_blowup():
    # equity 100 -> 20 (80% dd); cumulative PnL falls 0 -> -80 (ratio 1.0 >= 0.5).
    curve = eq([(0, 100), (1, 20), (2, 18)])
    pc = pnl([(0, 0), (1, -80), (2, -82)])
    t, ratio, n = forward_only_loss_confirmed_blowup(
        curve, pc, 0.7, 0.8, H, initial_peak=100.0, initial_peak_time=0)
    assert t == int(1 * H)
    assert ratio >= 0.5 and n == 0


def test_withdrawal_crater_is_skipped_then_real_blowup_found():
    # First crater (t=1): equity 100 -> 10 but PnL flat (withdrawal) -> skip, reset peak.
    # Rebuild to 200 (t=3), then equity 200 -> 30 with PnL crashing (t=4) -> blow-up.
    curve = eq([(0, 100), (1, 10), (2, 50), (3, 200), (4, 30)])
    pc = pnl([(0, 0), (1, 0), (2, 0), (3, 5), (4, -180)])
    t, ratio, n = forward_only_loss_confirmed_blowup(
        curve, pc, 0.7, 0.8, H, initial_peak=100.0, initial_peak_time=0)
    assert t == int(4 * H)        # the genuine loss crater, not the early withdrawal
    assert n == 1                  # one withdrawal crater was skipped
    assert ratio >= 0.5


def test_pure_withdrawal_never_blows_up():
    # Equity craters to ~0 but cumulative PnL never falls -> all withdrawals -> stable.
    curve = eq([(0, 100), (1, 5), (2, 0)])
    pc = pnl([(0, 50), (1, 50), (2, 50)])
    t, ratio, n = forward_only_loss_confirmed_blowup(
        curve, pc, 0.7, 0.8, H, initial_peak=100.0, initial_peak_time=0)
    assert t is None and n >= 1


def test_ratio_below_floor_is_withdrawal_above_is_loss():
    # equity drop 80; PnL drop 30 -> ratio 0.375 < 0.5 -> withdrawal (skip) -> stable.
    curve = eq([(0, 100), (1, 20)])
    pc = pnl([(0, 0), (1, -30)])
    t, _, _ = forward_only_loss_confirmed_blowup(
        curve, pc, 0.7, 0.8, H, initial_peak=100.0, initial_peak_time=0)
    assert t is None
    # PnL drop 50 -> ratio 0.625 >= 0.5 -> loss-confirmed blow-up.
    pc2 = pnl([(0, 0), (1, -50)])
    t2, ratio2, _ = forward_only_loss_confirmed_blowup(
        curve, pc2, 0.7, 0.8, H, initial_peak=100.0, initial_peak_time=0)
    assert t2 == int(1 * H) and ratio2 >= 0.5
