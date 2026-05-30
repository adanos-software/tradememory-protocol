from research.hyperliquid.trajectory import build_trajectory, meets_baseline


def test_build_trajectory_from_raw(raw_fills, raw_portfolio, raw_ledger, raw_orders):
    traj = build_trajectory("0xabc", raw_fills, raw_portfolio, raw_ledger, raw_orders)
    assert traj.address == "0xabc"
    assert len(traj.trades) == 2
    assert traj.stop_order_rate == 0.5
    assert traj.first_trade_ms == 1749513600000


def test_meets_baseline_requires_min_history_before_t(raw_fills, raw_portfolio, raw_ledger, raw_orders):
    traj = build_trajectory("0xabc", raw_fills, raw_portfolio, raw_ledger, raw_orders)
    assert meets_baseline(traj, t_event_ms=1749513600000 + 10**9,
                          min_trades=2, min_days=0.0) is True
    assert meets_baseline(traj, t_event_ms=1, min_trades=2, min_days=0.0) is False
