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


def _nearest_value(curve, t):
    """Value in a sorted [(time, value)] curve at the time nearest to t (or None)."""
    if not curve:
        return None
    return min(curve, key=lambda tv: abs(tv[0] - t))[1]


def forward_only_loss_confirmed_blowup(equity, pnl_curve, dd_pct, recovery_frac,
                                       recovery_horizon_ms, initial_peak, initial_peak_time,
                                       wd_ratio=0.5):
    """Forward-only blow-up time, but a >dd_pct drawdown counts only if its crater is
    LOSS-confirmed (pre-reg #6): the cumulative-PnL drop from the running-peak to the
    trough must be >= ``wd_ratio`` x the equity drop.

    Withdrawal-driven craters (equity fell but cumulative PnL did not) are NOT losses;
    such a crater RESETS the running peak to the trough value and the scan CONTINUES,
    so a genuine later loss-crater is still detected. This is the faithful join of the
    locked equity-drawdown rule (#4) and the withdrawal filter (#6): a blow-up is the
    first *loss-driven* >dd_pct account-death, whenever it occurs.

    Equity-only (no liquidation path — Stage 1 fetches no fills). ``initial_peak`` /
    ``initial_peak_time`` seed the running peak with the genuine pre-T0 peak so the
    drawdown and the PnL lookup are anchored to true history. ``pnl_curve`` is a sorted
    list of (time_ms, cumulative_pnl). Returns
    ``(blowup_time_ms_or_None, ratio_at_blowup_or_None, n_withdrawal_craters_skipped)``."""
    eq = sorted(equity, key=lambda p: p.time)
    peak = initial_peak
    peak_time = initial_peak_time
    n_skipped = 0
    for i, p in enumerate(eq):
        if p.value > peak:
            peak, peak_time = p.value, p.time
        if peak <= 0:
            continue
        if (peak - p.value) / peak <= dd_pct:
            continue
        # No recovery to recovery_frac*peak within the horizon (forward-only).
        recovered = False
        for q in eq[i:]:
            if q.time - p.time > recovery_horizon_ms:
                break
            if q.value >= recovery_frac * peak:
                recovered = True
                break
        if recovered:
            continue
        # Crater candidate (peak_time -> p.time): loss-confirmation.
        equity_drop = peak - p.value
        pnl_peak = _nearest_value(pnl_curve, peak_time)
        pnl_trough = _nearest_value(pnl_curve, p.time)
        ratio = None
        if pnl_peak is not None and pnl_trough is not None and equity_drop > 0:
            ratio = (pnl_peak - pnl_trough) / equity_drop
        if ratio is None or ratio >= wd_ratio:
            return p.time, ratio, n_skipped            # genuine loss-driven blow-up
        # Withdrawal crater: the lost capital was withdrawn, not traded away. Reset the
        # running peak to the post-withdrawal level and keep scanning for a real blow-up.
        n_skipped += 1
        peak, peak_time = p.value, p.time
    return None, None, n_skipped
