from research.hyperliquid.models import Trade, EquityPoint, LedgerEvent, Trajectory


def mk_trade(t_ms, coin="BTC", direction="Open Long", px=100.0, sz=1.0,
             closed_pnl=0.0, start_position=0.0, liq=False):
    return Trade(time=t_ms, coin=coin, direction=direction, px=px, sz=sz,
                 closed_pnl=closed_pnl, start_position=start_position, is_liquidation=liq)


def mk_eq(points):  # points: list[(t_ms, value)]
    return [EquityPoint(t, v) for t, v in points]


def mk_traj(trades=(), equity=(), ledger=(), stop_rate=0.0):
    trades = sorted(trades, key=lambda t: t.time)
    return Trajectory(address="0xtest", trades=list(trades), equity=list(equity),
                      ledger=list(ledger), stop_order_rate=stop_rate,
                      first_trade_ms=trades[0].time if trades else 0,
                      last_trade_ms=trades[-1].time if trades else 0)
