from __future__ import annotations
from research.hyperliquid.models import Trajectory
from research.hyperliquid.normalize import (
    normalize_fills, equity_curve, ledger_events, stop_order_rate)


def build_trajectory(address, raw_fills, raw_portfolio, raw_ledger, raw_orders,
                     period="perpAllTime"):
    trades = normalize_fills(raw_fills)
    eq = equity_curve(raw_portfolio, period=period)
    led = ledger_events(raw_ledger)
    rate = stop_order_rate(raw_orders)
    first = trades[0].time if trades else 0
    last = trades[-1].time if trades else 0
    return Trajectory(address=address, trades=trades, equity=eq, ledger=led,
                      stop_order_rate=rate, first_trade_ms=first, last_trade_ms=last)


def meets_baseline(traj, t_event_ms, min_trades, min_days):
    """Require enough pre-event history so the detector has a real baseline (spec 6.4)."""
    pre = [t for t in traj.trades if t.time < t_event_ms]
    if len(pre) < min_trades:
        return False
    if not pre:
        return False
    span_days = (t_event_ms - pre[0].time) / 86_400_000
    return span_days >= min_days
