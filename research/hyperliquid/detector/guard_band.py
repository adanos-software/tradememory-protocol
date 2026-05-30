"""Guard band: equity-health + pre-first-liquidation gate.

is_early returns True only when the alert occurs in the "early warning" zone:
  (a) equity is still healthy (>= guard_x * running_peak), AND
  (b) no liquidation has yet occurred for this master
       (first_liq_ms is None OR bucket_end_ms < first_liq_ms).

This separates predictive alerts (actionable) from post-disaster alerts
(too late to protect followers).
"""
from __future__ import annotations


def is_early(
    equity: float,
    running_peak: float,
    bucket_end_ms: int,
    first_liq_ms: int | None,
    guard_x: float,
) -> bool:
    """Return True iff the alert is in the early-warning guard band.

    Parameters
    ----------
    equity : float
        Account equity at this bucket's close.
    running_peak : float
        Maximum equity seen so far (including this bucket).
    bucket_end_ms : int
        Timestamp (ms) of this bucket's close.
    first_liq_ms : int | None
        Timestamp (ms) of the master's first liquidation, or None if none yet.
    guard_x : float
        Minimum equity-to-peak ratio to count as "healthy" (e.g. 0.70).

    Returns
    -------
    bool
    """
    if running_peak <= 0:
        return False
    if equity / running_peak < guard_x:
        return False
    if first_liq_ms is not None and bucket_end_ms >= first_liq_ms:
        return False
    return True
