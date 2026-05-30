from __future__ import annotations
from research.hyperliquid.models import Trade, EquityPoint, LedgerEvent


def normalize_fills(raw):
    out = []
    for f in raw:
        out.append(Trade(
            time=int(f["time"]), coin=f["coin"], direction=f.get("dir", ""),
            px=float(f["px"]), sz=float(f["sz"]),
            closed_pnl=float(f.get("closedPnl", 0.0)),
            start_position=float(f.get("startPosition", 0.0)),
            is_liquidation=("liquidation" in f)))
    return sorted(out, key=lambda t: t.time)


def equity_curve(raw_portfolio, period="perpAllTime"):
    by_period = {p[0]: p[1] for p in raw_portfolio}
    avh = by_period.get(period, {}).get("accountValueHistory", [])
    pts = [EquityPoint(int(t), float(v)) for t, v in avh]
    return sorted(pts, key=lambda p: p.time)


def drawdown_series(eq):
    out, peak = [], float("-inf")
    for p in eq:
        peak = max(peak, p.value)
        out.append(0.0 if peak <= 0 else (peak - p.value) / peak)
    return out


def ledger_events(raw):
    out = []
    for u in raw:
        d = u["delta"]
        amt = d.get("usdc", d.get("amount", 0.0))
        out.append(LedgerEvent(int(u["time"]), d["type"], float(amt)))
    return sorted(out, key=lambda e: e.time)


def stop_order_rate(raw_orders):
    if not raw_orders:
        return 0.0
    n_stop = sum(1 for o in raw_orders
                 if o.get("isTrigger") or o.get("isPositionTpsl"))
    return n_stop / len(raw_orders)


def order_events(raw_orders):
    """Normalise raw order records into a flat list of dicts.

    Each output dict has keys:
      coin       : str
      ts         : int  (epoch ms)
      is_trigger : bool (True if isTrigger or isPositionTpsl)

    Additive — does not alter any existing normalize functions.
    """
    out = []
    for o in raw_orders:
        out.append({
            "coin": o["coin"],
            "ts": int(o["timestamp"]),
            "is_trigger": bool(o.get("isTrigger") or o.get("isPositionTpsl")),
        })
    return out
