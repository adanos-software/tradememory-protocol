"""Plan 3 Stage 1 — equity-only cohort labeling on the frozen universe (SCALED run).

Reads `universe_addrs.txt` (a scaled sample of the >=$25k leaderboard universe),
fetches ONLY `portfolio` (accountValueHistory) per address (1 call/addr, reaches
pre-T0 even when fills hit the 10k cap), and labels each as blow-up / stable using
the forward-only equity rule against the genuine pre-T0 peak.

This is the cheap labeling stage of the pre-reg #10 two-stage design. Stage 2
(full trajectory + behavioral primitives) runs only on the labeled cohort.

SCALED / PROVISIONAL: this is a ~1.2k-address indicative run for an end-to-end
"full picture", NOT the full-universe pre-registered run. dd_pct/T0/window match
pre-reg Part 1 so the numbers are comparable.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from research.hyperliquid.normalize import equity_curve
from research.hyperliquid.blowup import forward_only_blowup_time

API = "https://api.hyperliquid.xyz/info"
ADDRS = Path("research/hyperliquid/universe_addrs.txt")
OUT = Path("research/hyperliquid/cohort_stage1.json")
PROGRESS = Path("research/hyperliquid/_stage1_progress.txt")

# Pre-reg Part 1 params
T0_MS = int(datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
WINDOW_END_MS = int(datetime(2026, 4, 30, tzinfo=timezone.utc).timestamp() * 1000)
DD_PCT = 0.70
RECOVERY_FRAC = 0.80
RECOVERY_HORIZON_MS = 30 * 86_400_000
RATE_DELAY_S = 0.4
MARKET_EVENT_TAU = 0.03  # a UTC day is "market-event" if >= 3% of the universe craters


def robust_post(body, max_retry=6):
    delay = 1.0
    for attempt in range(max_retry):
        try:
            req = urllib.request.Request(
                API, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "tm-research/0.1"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retry - 1:
                time.sleep(delay); delay *= 2; continue
            raise
        except Exception:
            if attempt < max_retry - 1:
                time.sleep(delay); delay *= 2; continue
            raise
    raise RuntimeError("max retry exceeded")


def _utc_day(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def main():
    addrs = [a.strip() for a in ADDRS.read_text().splitlines()
             if a.strip() and not a.strip().startswith("#")]
    members = []
    errors = 0
    excluded_no_equity = 0
    start = time.time()

    for i, addr in enumerate(addrs):
        try:
            port = robust_post({"type": "portfolio", "user": addr})
            eq = equity_curve(port)  # full accountValueHistory (perpAllTime)
            if not eq:
                excluded_no_equity += 1
                continue
            pre = [p.value for p in eq if p.time < T0_MS]
            pre_t0_peak = max(pre) if pre else float("-inf")
            post_eq = [p for p in eq if p.time >= T0_MS]
            if not post_eq:
                excluded_no_equity += 1
                continue
            t_blow = forward_only_blowup_time(
                post_eq, [], DD_PCT, RECOVERY_FRAC, RECOVERY_HORIZON_MS,
                initial_peak=pre_t0_peak)
            if t_blow is not None and t_blow > WINDOW_END_MS:
                t_blow = None
            members.append({
                "address": addr,
                "label": "blowup" if t_blow is not None else "stable",
                "blowup_time": t_blow,
                "event_cluster": _utc_day(t_blow) if t_blow is not None else None,
                "pre_t0_peak": pre_t0_peak if pre_t0_peak != float("-inf") else None,
                "n_eq_pre": len(pre),
                "n_eq_post": len(post_eq),
            })
        except Exception as e:
            errors += 1
        if (i + 1) % 25 == 0:
            el = time.time() - start
            PROGRESS.write_text(
                f"{i+1}/{len(addrs)} done | {len(members)} labeled | "
                f"{errors} errors | {excluded_no_equity} no-equity | {el:.0f}s\n")
        time.sleep(RATE_DELAY_S)

    blowups = [m for m in members if m["label"] == "blowup"]
    stable = [m for m in members if m["label"] == "stable"]
    # crash-day histogram + market-event tagging
    day_hist = {}
    for m in blowups:
        day_hist[m["event_cluster"]] = day_hist.get(m["event_cluster"], 0) + 1
    n_active = max(1, len(members))
    market_event_days = {d for d, c in day_hist.items() if c / n_active >= MARKET_EVENT_TAU}
    idiosyncratic = [m for m in blowups if m["event_cluster"] not in market_event_days]

    payload = {
        "scaled_provisional": True,
        "t0_ms": T0_MS, "window_end_ms": WINDOW_END_MS,
        "dd_pct": DD_PCT, "market_event_tau": MARKET_EVENT_TAU,
        "n_sampled": len(addrs), "n_labeled": len(members),
        "n_errors": errors, "n_excluded_no_equity": excluded_no_equity,
        "n_blowup": len(blowups), "n_stable": len(stable),
        "base_rate": len(blowups) / n_active,
        "effective_n_events": len({m["event_cluster"] for m in blowups if m["event_cluster"]}),
        "crash_day_histogram": dict(sorted(day_hist.items(), key=lambda kv: -kv[1])),
        "market_event_days": sorted(market_event_days),
        "n_idiosyncratic_blowups": len(idiosyncratic),
        "members": members,
    }
    OUT.write_text(json.dumps(payload, indent=2))
    PROGRESS.write_text(
        f"DONE in {time.time()-start:.0f}s | labeled={len(members)} blowups={len(blowups)} "
        f"idiosyncratic={len(idiosyncratic)} base_rate={payload['base_rate']:.3f} "
        f"eff_n={payload['effective_n_events']} errors={errors}\n")
    print(PROGRESS.read_text())


if __name__ == "__main__":
    main()
