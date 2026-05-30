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


def anchors_flat(median=0.0, mad=1.0):
    """Per-primitive anchors (median+MAD) shared by the synthetic-stream tests."""
    from research.hyperliquid.detector.config import PRIMITIVES, AXES
    return {a: {p: {"median": median, "mad": mad} for p in PRIMITIVES[a]} for a in AXES}


def identity_cov():
    """9x9 identity cross-primitive correlation matrix keyed by primitive name."""
    from research.hyperliquid.detector.config import PRIMITIVES, AXES
    keys = [p for a in AXES for p in PRIMITIVES[a]]
    return {k: {j: (1.0 if k == j else 0.0) for j in keys} for k in keys}
