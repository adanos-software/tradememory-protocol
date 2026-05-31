"""Non-trivial EARLY baselines B1/B2/B3 (+ the B0 too-late reference).

These are the comparison bar for Claim A: each is a plausible, non-trivial rule a
practitioner might use to flag a master early, evaluated under the SAME guard
band as the detector (the alert only counts if it fires in the early-warning
zone -- equity still healthy AND before the first liquidation). The headline is
lead-time OVER these baselines, so they must be honest and reasonably strong, not
strawmen.

Each B1/B2/B3 returns the first guard-banded bucket's ``end_ms`` where its rule
trips, else None.

  B1 b1_leverage_percentile  : the master's own early-window (first third) p90 of
      leverage; fire the first guard-banded bucket where leverage exceeds it.
  B2 b2_drawdown_velocity    : per-bucket drawdown-from-peak, first-differenced
      into a velocity (the ACCELERATION of drawdown, not its level); fire the
      first guard-banded bucket where velocity exceeds the early-window p90
      velocity.
  B3 b3_leverage_up_and_add  : fire the first guard-banded bucket where leverage
      rose vs the previous bucket AND loser_add_count > 0 (adding to losers while
      levering up -- a classic tilt tell).

  B0 b0_too_late             : the first bucket below guard_x equity (the first
      NON-healthy bucket). This is the "too late" reference (lead ~0): by the time
      equity has cratered, followers are already exposed. NOT guard-banded.

Guard band: each baseline tracks running_peak over confirmed (non-None) equity
and uses detector.guard_band.is_early(equity, running_peak, end_ms, first_liq_ms,
guard_x) -- identical to the detector's own gate -- to decide whether a bucket is
in the early-warning zone. None-equity buckets are never guard-banded (is_early
returns False) and never advance the running peak (detector.py rule).

Imports: stdlib + research.hyperliquid.* only. No numpy, no tradememory.owm.*.
"""
from __future__ import annotations

from research.hyperliquid.detector.guard_band import is_early

__all__ = [
    "b0_too_late",
    "b1_leverage_percentile",
    "b2_drawdown_velocity",
    "b3_leverage_up_and_add",
]


def _percentile(values: list[float], q: float) -> float:
    """Linear-interpolation percentile (type-7 / numpy default), pure Python.

    q in [0, 1]. For n==1 returns the single value; for q at the extremes returns
    min/max. Empty input is a programming error (callers guard with len check).
    """
    s = sorted(values)
    n = len(s)
    if n == 1:
        return s[0]
    # rank position on [0, n-1]
    pos = q * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _early_window_end(n: int) -> int:
    """Index (exclusive) of the master's own early window = first third.

    At least 1 bucket so a percentile is always definable for a non-empty series.
    """
    return max(1, n // 3)


def _running_peaks(series: list[dict]) -> list[float | None]:
    """Running peak of confirmed (non-None) equity at each bucket.

    None-equity buckets do not advance the peak; their entry is the running peak
    *so far* (or None if no equity has yet been seen). Mirrors detector.py.
    """
    peaks: list[float | None] = []
    peak: float | None = None
    for b in series:
        eq = b["equity"]
        if eq is not None:
            peak = eq if peak is None else max(peak, eq)
        peaks.append(peak)
    return peaks


def _guard_banded(b: dict, peak: float | None, first_liq_ms: int | None,
                  guard_x: float) -> bool:
    """True iff this bucket is in the early-warning zone."""
    eq = b["equity"]
    if eq is None or peak is None or peak <= 0:
        return False
    return is_early(eq, peak, b["end_ms"], first_liq_ms, guard_x)


# ---------------------------------------------------------------------------
# B1 -- leverage exceeds early-window p90
# ---------------------------------------------------------------------------
def b1_leverage_percentile(series: list[dict], first_liq_ms: int | None,
                           guard_x: float) -> int | None:
    """First guard-banded bucket where leverage > early-window p90 leverage."""
    n = len(series)
    if n == 0:
        return None
    ew_end = _early_window_end(n)
    early_lev = [series[i]["prim"]["leverage"] for i in range(ew_end)]
    if not early_lev:
        return None
    thresh = _percentile(early_lev, 0.90)

    peaks = _running_peaks(series)
    for i in range(n):
        b = series[i]
        if b["prim"]["leverage"] > thresh and _guard_banded(
            b, peaks[i], first_liq_ms, guard_x
        ):
            return b["end_ms"]
    return None


# ---------------------------------------------------------------------------
# B2 -- drawdown velocity (acceleration of DD, not its level)
# ---------------------------------------------------------------------------
def b2_drawdown_velocity(series: list[dict], first_liq_ms: int | None,
                         guard_x: float) -> int | None:
    """First guard-banded bucket where drawdown-velocity > early-window p90.

    Drawdown fraction at bucket i = (peak_i - equity_i) / peak_i over confirmed
    equity. Velocity at bucket i = dd_i - dd_{i-1} (first difference), defined
    only between consecutive confirmed-equity buckets; buckets with None equity
    carry the previous dd forward for the difference (no spurious velocity).
    """
    n = len(series)
    if n == 0:
        return None
    peaks = _running_peaks(series)

    # Drawdown fraction per bucket (None where equity/peak undefined).
    dd: list[float | None] = []
    for i in range(n):
        eq = series[i]["equity"]
        pk = peaks[i]
        if eq is None or pk is None or pk <= 0:
            dd.append(None)
        else:
            dd.append((pk - eq) / pk)

    # Velocity vs the most recent defined dd (carry-forward across None gaps).
    velocity: list[float | None] = [None] * n
    prev_dd: float | None = None
    for i in range(n):
        if dd[i] is not None:
            if prev_dd is not None:
                velocity[i] = dd[i] - prev_dd
            prev_dd = dd[i]
        # if dd[i] is None: leave velocity None, keep prev_dd as last defined

    # Early-window p90 velocity (over defined velocities in the first third).
    ew_end = _early_window_end(n)
    early_vel = [velocity[i] for i in range(ew_end) if velocity[i] is not None]
    if not early_vel:
        # no defined early velocity (e.g. all-None early equity): fall back to 0
        thresh = 0.0
    else:
        thresh = _percentile(early_vel, 0.90)

    for i in range(n):
        if velocity[i] is None:
            continue
        if velocity[i] > thresh and _guard_banded(
            series[i], peaks[i], first_liq_ms, guard_x
        ):
            return series[i]["end_ms"]
    return None


# ---------------------------------------------------------------------------
# B3 -- leverage up AND adding to losers
# ---------------------------------------------------------------------------
def b3_leverage_up_and_add(series: list[dict], first_liq_ms: int | None,
                           guard_x: float) -> int | None:
    """First guard-banded bucket where leverage rose vs previous AND
    loser_add_count > 0."""
    n = len(series)
    if n == 0:
        return None
    peaks = _running_peaks(series)
    prev_lev: float | None = None
    for i in range(n):
        b = series[i]
        lev = b["prim"]["leverage"]
        add = b["prim"]["loser_add_count"]
        lever_up = prev_lev is not None and lev > prev_lev
        if lever_up and add > 0 and _guard_banded(
            b, peaks[i], first_liq_ms, guard_x
        ):
            return b["end_ms"]
        prev_lev = lev
    return None


# ---------------------------------------------------------------------------
# B0 -- too-late reference (first NON-healthy bucket)
# ---------------------------------------------------------------------------
def b0_too_late(series: list[dict], guard_x: float) -> int | None:
    """First bucket whose equity has dropped below guard_x * running_peak.

    The "too late" reference: lead ~0 because the drawdown has already happened.
    NOT guard-banded (that is precisely the point). None-equity buckets are
    skipped (cannot confirm a drop).
    """
    n = len(series)
    if n == 0:
        return None
    peaks = _running_peaks(series)
    for i in range(n):
        eq = series[i]["equity"]
        pk = peaks[i]
        if eq is None or pk is None or pk <= 0:
            continue
        if eq < guard_x * pk:
            return series[i]["end_ms"]
    return None
