from __future__ import annotations
from research.hyperliquid.models import EquityPoint, Trade


def forward_only_blowup_time(equity, trades, dd_pct, recovery_frac, recovery_horizon_ms,
                             initial_peak=float("-inf")):
    """Earliest blow-up time T using ONLY data within [candidate, candidate+horizon].
    (a) first equity bar whose drawdown-from-running-peak > dd_pct AND which does not
        recover above recovery_frac*peak within recovery_horizon_ms; or
    (b) first liquidation fill - whichever is earlier.
    `initial_peak` seeds the running peak with the genuine (e.g. pre-T0) peak so drawdown
    is measured against true history, not just the sliced window (see label_cohort)."""
    liq_t = next((t.time for t in sorted(trades, key=lambda x: x.time)
                  if t.is_liquidation), None)

    eq = sorted(equity, key=lambda p: p.time)
    dd_t = None
    peak = initial_peak
    for i, p in enumerate(eq):
        peak = max(peak, p.value)
        if peak <= 0:
            continue
        dd = (peak - p.value) / peak
        if dd > dd_pct:
            recovered = False
            for q in eq[i:]:
                if q.time - p.time > recovery_horizon_ms:
                    break
                if q.value >= recovery_frac * peak:
                    recovered = True
                    break
            if not recovered:
                dd_t = p.time
                break

    candidates = [t for t in (liq_t, dd_t) if t is not None]
    return min(candidates) if candidates else None
