from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Bucket:
    start_ms: int
    end_ms: int
    fills: list = field(default_factory=list)
    ledger: list = field(default_factory=list)
    equity_end: float | None = None


def bucketize(traj, origin_ms, end_ms, bucket_ms):
    if origin_ms >= end_ms:
        return []
    n = (end_ms - origin_ms + bucket_ms - 1) // bucket_ms
    buckets = [Bucket(origin_ms + i * bucket_ms, origin_ms + (i + 1) * bucket_ms)
               for i in range(n)]

    def idx(t):
        return (t - origin_ms) // bucket_ms

    for tr in traj.trades:
        if origin_ms <= tr.time < end_ms:
            buckets[idx(tr.time)].fills.append(tr)
    for ev in traj.ledger:
        if origin_ms <= ev.time < end_ms:
            buckets[idx(ev.time)].ledger.append(ev)

    # Carry-forward equity: bucket.equity_end = latest point with time <= end_ms.
    # Pre-origin equity points (time < origin_ms) are INTENTIONALLY carried into bucket 0 as
    # the entry-time account-value reference (the master's equity when the window opens), so
    # the guard band's running_peak reflects the genuine pre-window peak.
    eq = sorted(traj.equity, key=lambda p: p.time)
    j, last = 0, None
    for b in buckets:
        while j < len(eq) and eq[j].time <= b.end_ms:
            last = eq[j].value
            j += 1
        b.equity_end = last
    return buckets
