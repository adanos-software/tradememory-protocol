from __future__ import annotations
from datetime import datetime, timezone
from research.hyperliquid.models import CohortMember, CohortManifest
from research.hyperliquid.blowup import forward_only_blowup_time
from research.hyperliquid.trajectory import meets_baseline


def _utc_day(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def label_cohort(trajectories, t0_ms, window_end_ms, dd_pct, recovery_frac,
                 recovery_horizon_ms, min_trades, min_days):
    man = CohortManifest(t0_ms=t0_ms, window_end_ms=window_end_ms)
    for traj in trajectories:
        if not traj.trades and not traj.equity:
            man.excluded_no_data += 1
            continue
        # Inclusion: enough warm-up history BEFORE T0 (outcome-independent).
        if not meets_baseline(traj, t_event_ms=t0_ms,
                              min_trades=min_trades, min_days=min_days):
            man.excluded_short_baseline += 1
            continue
        # Outcome from post-T0 data only; drawdown vs the GENUINE peak (seed pre-T0 max).
        pre_t0_peak = max((p.value for p in traj.equity if p.time < t0_ms),
                          default=float("-inf"))
        post_eq = [p for p in traj.equity if p.time >= t0_ms]
        post_tr = [t for t in traj.trades if t.time >= t0_ms]
        t_blow = forward_only_blowup_time(post_eq, post_tr, dd_pct, recovery_frac,
                                          recovery_horizon_ms, initial_peak=pre_t0_peak)
        if t_blow is not None and t_blow > window_end_ms:
            t_blow = None
        pre = [t for t in traj.trades if t.time < t0_ms]
        man.members.append(CohortMember(
            address=traj.address,
            label="blowup" if t_blow is not None else "stable",
            blowup_time=t_blow,
            event_cluster=_utc_day(t_blow) if t_blow is not None else None,
            baseline_trades=len(pre),
            baseline_days=(t0_ms - pre[0].time) / 86_400_000 if pre else 0.0))
    return man
