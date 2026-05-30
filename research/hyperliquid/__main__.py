from __future__ import annotations
import argparse
import json
from dataclasses import asdict
from pathlib import Path
from research.hyperliquid.client import HyperliquidClient
from research.hyperliquid.trajectory import build_trajectory
from research.hyperliquid.universe import label_cohort


def run(addrs_path, t0_ms, window_end_ms, out_path, transport=None,
        archive_dir="research/hyperliquid/_archive", dd_pct=0.5, recovery_frac=0.8,
        recovery_horizon_ms=86_400_000, min_trades=30, min_days=7.0):
    c = HyperliquidClient(transport=transport, archive_dir=archive_dir)
    addrs = [a.strip() for a in Path(addrs_path).read_text().splitlines()
             if a.strip() and not a.strip().startswith("#")]
    trajs, n_truncated = [], 0
    for a in addrs:
        fills = c.fetch_user_fills_by_time(a, start_ms=0)
        if c.last_fetch_truncated:
            n_truncated += 1
        trajs.append(build_trajectory(a, fills, c.fetch_portfolio(a),
                                      c.fetch_ledger(a, start_ms=0),
                                      c.fetch_historical_orders(a)))
    man = label_cohort(trajs, t0_ms, window_end_ms, dd_pct, recovery_frac,
                       recovery_horizon_ms, min_trades, min_days)
    payload = {"t0_ms": man.t0_ms, "window_end_ms": man.window_end_ms,
               "base_rate": man.base_rate, "effective_n_events": man.effective_n_events,
               "n_blowup": len(man.blowups), "n_stable": len(man.stable),
               "excluded_short_baseline": man.excluded_short_baseline,
               "excluded_no_data": man.excluded_no_data,
               "n_truncated_10k_cap": n_truncated,
               "members": [asdict(m) for m in man.members]}
    Path(out_path).write_text(json.dumps(payload, indent=2))
    return man


if __name__ == "__main__":  # pragma: no cover
    p = argparse.ArgumentParser()
    p.add_argument("--addrs", required=True)
    p.add_argument("--t0-ms", type=int, required=True)
    p.add_argument("--window-end-ms", type=int, required=True)
    p.add_argument("--out", default="research/hyperliquid/cohort.json")
    p.add_argument("--min-trades", type=int, default=30)
    p.add_argument("--min-days", type=float, default=7.0)
    a = p.parse_args()
    man = run(a.addrs, a.t0_ms, a.window_end_ms, a.out,
              min_trades=a.min_trades, min_days=a.min_days)
    print(f"members={len(man.members)} base_rate={man.base_rate:.3f} "
          f"effective_n_events={man.effective_n_events} "
          f"excluded_short={man.excluded_short_baseline}")
