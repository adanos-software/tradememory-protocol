"""Plan 3 Phase-5 cohort behavioral fetch (SCALED / PROVISIONAL).

Reads cohort_stage1.json, picks a capped sub-cohort (idiosyncratic blow-ups +
matched stable masters), fetches full trajectory, and stores per-master per-bucket
behavioral series (9 primitives + equity_end + bucket_end_ms) to cohort_behavioral.json
so the experiment runner can replay A/B/ablation without re-fetching.

Uses the EARLY-WINDOW baseline approach (decided 2026-05-31): no pre-T0 requirement,
so high-freq masters are kept. Buckets are computed over each master's in-observation
window [max(first_trade, T0), blowup_time or window_end).

PROVISIONAL: capped sub-cohort, scaled run — not the full-universe pre-reg run.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from research.hyperliquid.stage2_behavioral import fetch_trajectory, coin_sigmas, _split_bucket
from research.hyperliquid.detector.bucketing import bucketize
from research.hyperliquid.detector.primitives import PrimitiveState
from research.hyperliquid.normalize import order_events

STAGE1 = Path("research/hyperliquid/cohort_stage1.json")
OUT = Path("research/hyperliquid/cohort_behavioral.json")
PROGRESS = Path("research/hyperliquid/_behavioral_progress.txt")

T0_MS = int(datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
WINDOW_END_MS = int(datetime(2026, 4, 30, tzinfo=timezone.utc).timestamp() * 1000)
BUCKET_MS = 4 * 3600 * 1000
RATE_DELAY_S = 0.4
CAP_BLOWUP = 120
CAP_STABLE = 120


def main():
    data = json.loads(STAGE1.read_text())
    members = data["members"]
    mev = set(data.get("market_event_days", []))

    idio_blow = [m for m in members if m["label"] == "blowup"
                 and m["event_cluster"] not in mev and m["blowup_time"]][:CAP_BLOWUP]
    stable = [m for m in members if m["label"] == "stable"
              and m.get("n_eq_pre", 0) >= 2][:CAP_STABLE]
    cohort = idio_blow + stable
    print(f"cohort: {len(idio_blow)} idiosyncratic blowups + {len(stable)} stable = {len(cohort)}")

    out = []
    errors = 0
    start = time.time()
    for i, m in enumerate(cohort):
        try:
            traj, orders = fetch_trajectory(m["address"])
            if not traj.trades:
                continue
            origin = max(traj.trades[0].time, T0_MS)
            end = m["blowup_time"] if m["blowup_time"] else WINDOW_END_MS
            if origin >= end:
                continue
            oe = order_events(orders)
            buckets = bucketize(traj, origin, end, BUCKET_MS, orders=oe)
            cs, pooled = coin_sigmas(traj)
            st = PrimitiveState(coin_sigma=cs, pooled_sigma=pooled)
            series = []
            for b in buckets:
                pv = st.bucket_values(b)
                series.append({"prim": pv, "equity": b.equity_end, "end_ms": b.end_ms})
            first_liq = next((t.time for t in sorted(traj.trades, key=lambda x: x.time)
                              if t.is_liquidation), None)
            out.append({
                "address": m["address"],
                "label": m["label"],
                "split": _split_bucket(m["address"]),
                "blowup_time": m["blowup_time"],
                "event_cluster": m["event_cluster"],
                "first_liq_ms": first_liq,
                "n_buckets": len(series),
                "series": series,
            })
        except Exception as e:
            errors += 1
        if (i + 1) % 10 == 0:
            PROGRESS.write_text(
                f"{i+1}/{len(cohort)} | kept={len(out)} | errors={errors} | {time.time()-start:.0f}s\n")
        time.sleep(RATE_DELAY_S)

    payload = {
        "scaled_provisional": True,
        "t0_ms": T0_MS, "window_end_ms": WINDOW_END_MS, "bucket_ms": BUCKET_MS,
        "n_blowup": sum(1 for m in out if m["label"] == "blowup"),
        "n_stable": sum(1 for m in out if m["label"] == "stable"),
        "n_errors": errors,
        "masters": out,
    }
    OUT.write_text(json.dumps(payload))
    PROGRESS.write_text(
        f"DONE in {time.time()-start:.0f}s | kept={len(out)} "
        f"(blowup={payload['n_blowup']} stable={payload['n_stable']}) errors={errors}\n")
    print(PROGRESS.read_text())


if __name__ == "__main__":
    main()
