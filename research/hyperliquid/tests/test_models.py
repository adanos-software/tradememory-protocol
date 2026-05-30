from research.hyperliquid.models import Trade, EquityPoint, Trajectory


def test_trade_is_liquidation_flag():
    t = Trade(time=1, coin="BTC", direction="Close Long", px=1.0, sz=1.0,
              closed_pnl=-5.0, start_position=1.0, is_liquidation=True)
    assert t.is_liquidation


def test_trajectory_holds_components():
    traj = Trajectory(address="0xabc", trades=[], equity=[EquityPoint(1, 100.0)],
                      ledger=[], stop_order_rate=0.5, first_trade_ms=1, last_trade_ms=1)
    assert traj.address == "0xabc"
    assert traj.equity[0].value == 100.0
