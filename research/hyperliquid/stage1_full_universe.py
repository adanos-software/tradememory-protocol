"""Full-universe Stage-1 labeling — the PRE-REGISTERED run (pre-reg Part 1, locked 92e343c).

Generalizes `stage1_label.py` from the scaled 1.2k sample to the FULL leaderboard
universe (~37.9k addrs). For each address we fetch ONLY `portfolio` (one call,
reaches pre-T0 even when fills hit the 10k cap) and apply the locked Part-1 rules
*faithfully* — the difference between the exploratory and the pre-registered run:

  1. Universe qualification (outcome-blind, computed from history not current value):
       pre-T0 peak perp account value >= $25,000  AND  >= 2 pre-T0 equity points.
     (We deliberately do NOT pre-filter on *current* account value: blown-up
      masters now sit below $25k and that filter would drop exactly the events
      the study needs — survivorship bias.)
  2. Forward-only blow-up label: peak-to-trough drawdown > 70% with no recovery to
     80% of peak within 30 days (seeded with the genuine pre-T0 peak). Equity-only
     at this stage (no fills fetched), so this is the "equity-threshold path".
  3. Withdrawal filter (pre-reg #6): an equity-threshold blow-up counts only if the
     cumulative-PnL drop across the crater is >= 0.5 x the equity drop. Craters that
     are mostly withdrawals (ratio < 0.5) are reclassified `withdrawal` and excluded
     from BOTH the blow-up and stable cohorts. (Scoping median ratio 0.92.)
  4. Market-event-day tagging: a UTC day is a market-event day if >= 3% of the active
     (qualified) universe craters on it; those blow-ups are separated from idiosyncratic.

Robustness for a multi-hour 37.9k-call run:
  * concurrent workers with a single global rate gate (requests spaced >= MIN_INTERVAL),
  * robust 429 exponential backoff,
  * per-address checkpoint to a JSONL (resume skips finished addrs),
  * aggregation reads the JSONL, so an interrupted run can still be aggregated.

CLI:
  python research/hyperliquid/stage1_full_universe.py             # full run + aggregate
  python research/hyperliquid/stage1_full_universe.py --limit 30  # dry-run on first 30 addrs
  python research/hyperliquid/stage1_full_universe.py --aggregate-only
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from research.hyperliquid.normalize import equity_curve
from research.hyperliquid.blowup import forward_only_loss_confirmed_blowup

API = "https://api.hyperliquid.xyz/info"
ADDRS = Path("research/hyperliquid/universe_addrs_full.txt")
JSONL = Path("research/hyperliquid/cohort_stage1_full.jsonl")
OUT = Path("research/hyperliquid/cohort_stage1.json")
PROGRESS = Path("research/hyperliquid/_stage1_progress.txt")

# Pre-reg Part 1 params (LOCKED 92e343c) — identical to the scaled run for comparability.
T0_MS = int(datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
WINDOW_END_MS = int(datetime(2026, 4, 30, tzinfo=timezone.utc).timestamp() * 1000)
DD_PCT = 0.70
RECOVERY_FRAC = 0.80
RECOVERY_HORIZON_MS = 30 * 86_400_000
PEAK_FLOOR = 25_000.0          # pre-reg #1: pre-T0 peak >= $25k
MIN_PRE_T0_POINTS = 2          # pre-reg #1: >= 2 pre-T0 equity points
WITHDRAWAL_RATIO = 0.5         # pre-reg #6: PnL-drop / equity-drop must be >= 0.5
MARKET_EVENT_TAU = 0.03        # pre-reg #7: market-event day if >= 3% of universe craters

# Throughput: 5 workers, requests spaced >= 0.18s globally (~5.5 req/s aggregate).
# Scaled run did 2.5 req/s single-thread with 0 errors; backoff absorbs the occasional 429.
N_WORKERS = 5
MIN_INTERVAL = 0.18

_rate_lock = threading.Lock()
_next_slot = [0.0]
_file_lock = threading.Lock()
_counter_lock = threading.Lock()
_stats = {"done": 0, "blowup": 0, "stable": 0, "wd_skipped": 0,
          "below_peak": 0, "short_pre": 0, "no_data": 0, "errors": 0}


def _rate_gate():
    with _rate_lock:
        now = time.monotonic()
        slot = max(now, _next_slot[0] + MIN_INTERVAL)
        _next_slot[0] = slot
        wait = slot - now
    if wait > 0:
        time.sleep(wait)


def robust_post(body, max_retry=7):
    delay = 1.0
    for attempt in range(max_retry):
        _rate_gate()
        try:
            req = urllib.request.Request(
                API, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "tm-research/0.1"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < max_retry - 1:
                time.sleep(delay); delay = min(delay * 2, 30.0); continue
            raise
        except Exception:
            if attempt < max_retry - 1:
                time.sleep(delay); delay = min(delay * 2, 30.0); continue
            raise
    raise RuntimeError("max retry exceeded")


def _pnl_curve(raw_portfolio, period="perpAllTime"):
    by_period = {p[0]: p[1] for p in raw_portfolio}
    hist = by_period.get(period, {}).get("pnlHistory", [])
    return sorted(((int(t), float(v)) for t, v in hist), key=lambda x: x[0])


def _utc_day(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def label_one(addr):
    """Fetch portfolio, qualify, label (Option B: loss-confirmed forward scan).

    Returns a record dict (always has 'address')."""
    try:
        port = robust_post({"type": "portfolio", "user": addr})
    except Exception as e:  # noqa: BLE001
        return {"address": addr, "qualified": False, "reason": "error", "err": str(e)[:120]}
    eq = equity_curve(port)
    if not eq:
        return {"address": addr, "qualified": False, "reason": "no_equity"}
    pre = [p for p in eq if p.time < T0_MS]
    n_pre = len(pre)
    # Universe qualification (outcome-blind, computed from history not current value).
    if n_pre < MIN_PRE_T0_POINTS:
        return {"address": addr, "qualified": False, "reason": "short_pre_t0", "n_eq_pre": n_pre}
    pre_peak_pt = max(pre, key=lambda p: p.value)
    pre_peak = pre_peak_pt.value
    if pre_peak < PEAK_FLOOR:
        return {"address": addr, "qualified": False, "reason": "below_peak_floor",
                "n_eq_pre": n_pre, "pre_t0_peak": pre_peak}
    post_eq = [p for p in eq if p.time >= T0_MS]
    if not post_eq:
        return {"address": addr, "qualified": False, "reason": "no_post_t0",
                "n_eq_pre": n_pre, "pre_t0_peak": pre_peak}
    t_blow, ratio, n_skipped = forward_only_loss_confirmed_blowup(
        post_eq, _pnl_curve(port), DD_PCT, RECOVERY_FRAC, RECOVERY_HORIZON_MS,
        initial_peak=pre_peak, initial_peak_time=pre_peak_pt.time, wd_ratio=WITHDRAWAL_RATIO)
    if t_blow is not None and t_blow > WINDOW_END_MS:
        t_blow, ratio = None, None
    label = "blowup" if t_blow is not None else "stable"
    return {
        "address": addr,
        "qualified": True,
        "label": label,
        "blowup_time": t_blow,
        "event_cluster": _utc_day(t_blow) if t_blow is not None else None,
        "pre_t0_peak": pre_peak,
        "n_eq_pre": n_pre,
        "n_eq_post": len(post_eq),
        "withdrawal_ratio": ratio,            # PnL/equity ratio at the confirmed crater
        "withdrawal_craters_skipped": n_skipped,
    }


def _bump(rec):
    with _counter_lock:
        _stats["done"] += 1
        if not rec.get("qualified"):
            r = rec.get("reason")
            if r == "below_peak_floor":
                _stats["below_peak"] += 1
            elif r in ("short_pre_t0", "no_post_t0", "no_equity"):
                _stats["short_pre"] += 1 if r == "short_pre_t0" else 0
                _stats["no_data"] += 1 if r in ("no_post_t0", "no_equity") else 0
            elif r == "error":
                _stats["errors"] += 1
        else:
            _stats[rec["label"]] += 1
            _stats["wd_skipped"] += rec.get("withdrawal_craters_skipped", 0)


def _append(rec):
    line = json.dumps(rec)
    with _file_lock:
        with open(JSONL, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _write_progress(total, start):
    with _counter_lock:
        s = dict(_stats)
    el = time.time() - start
    rate = s["done"] / el if el > 0 else 0
    eta = (total - s["done"]) / rate / 60 if rate > 0 else 0
    PROGRESS.write_text(
        f"{s['done']}/{total} | blowup={s['blowup']} stable={s['stable']} "
        f"wd_skipped={s['wd_skipped']} | below_peak={s['below_peak']} short_pre={s['short_pre']} "
        f"no_data={s['no_data']} err={s['errors']} | {el:.0f}s {rate:.1f}/s ETA~{eta:.0f}m\n")


def run(limit=None):
    addrs = [a.strip().lower() for a in ADDRS.read_text(encoding="utf-8").splitlines()
             if a.strip() and not a.strip().startswith("#")]
    if limit:
        addrs = addrs[:limit]
    done = set()
    if JSONL.exists():
        for ln in JSONL.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    done.add(json.loads(ln)["address"])
                except Exception:  # noqa: BLE001
                    pass
    todo = [a for a in addrs if a not in done]
    print(f"universe={len(addrs)} already_done={len(done)} todo={len(todo)} "
          f"workers={N_WORKERS} interval={MIN_INTERVAL}s")
    if done:
        # Re-seed counters from the existing JSONL so progress/aggregate stay correct.
        for ln in JSONL.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    _bump(json.loads(ln))
                except Exception:  # noqa: BLE001
                    pass
    start = time.time()
    if not todo:
        print("nothing to fetch; all addresses already labeled")
        return
    with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
        futs = {ex.submit(label_one, a): a for a in todo}
        for i, fut in enumerate(as_completed(futs)):
            try:
                rec = fut.result()
            except Exception as e:  # noqa: BLE001
                rec = {"address": futs[fut], "qualified": False, "reason": "error", "err": str(e)[:120]}
            _append(rec)
            _bump(rec)
            if (i + 1) % 100 == 0:
                _write_progress(len(addrs), start)
    _write_progress(len(addrs), start)
    print("fetch complete:", PROGRESS.read_text().strip())


def aggregate():
    if not JSONL.exists():
        print("no JSONL to aggregate", file=sys.stderr)
        return
    recs = []
    for ln in JSONL.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            try:
                recs.append(json.loads(ln))
            except Exception:  # noqa: BLE001
                pass
    qualified = [r for r in recs if r.get("qualified")]
    members = [{
        "address": r["address"], "label": r["label"], "blowup_time": r["blowup_time"],
        "event_cluster": r["event_cluster"], "pre_t0_peak": r["pre_t0_peak"],
        "n_eq_pre": r["n_eq_pre"], "n_eq_post": r.get("n_eq_post"),
        "withdrawal_ratio": r.get("withdrawal_ratio"),
        "withdrawal_craters_skipped": r.get("withdrawal_craters_skipped", 0),
    } for r in qualified]
    blowups = [m for m in members if m["label"] == "blowup"]
    stable = [m for m in members if m["label"] == "stable"]
    n_active = max(1, len(members))  # qualified universe = blowup + stable

    day_hist = {}
    for m in blowups:
        day_hist[m["event_cluster"]] = day_hist.get(m["event_cluster"], 0) + 1
    market_event_days = {d for d, c in day_hist.items() if d and c / n_active >= MARKET_EVENT_TAU}
    idiosyncratic = [m for m in blowups if m["event_cluster"] not in market_event_days]

    # Withdrawal accounting (Option B): craters skipped because they were withdrawals,
    # not losses; and the loss-confirmation ratio distribution of the kept blow-ups.
    blow_ratios = sorted(m["withdrawal_ratio"] for m in blowups
                         if isinstance(m["withdrawal_ratio"], (int, float)))
    med_ratio = (blow_ratios[len(blow_ratios) // 2] if blow_ratios else None)
    withdrawal_accounting = {
        "total_withdrawal_craters_skipped": sum(m["withdrawal_craters_skipped"] for m in members),
        "masters_with_a_skipped_withdrawal": sum(1 for m in members if m["withdrawal_craters_skipped"] > 0),
        "blowup_loss_ratio_median": med_ratio,
    }

    exclusions = {
        "below_peak_floor": sum(1 for r in recs if r.get("reason") == "below_peak_floor"),
        "short_pre_t0": sum(1 for r in recs if r.get("reason") == "short_pre_t0"),
        "no_post_t0": sum(1 for r in recs if r.get("reason") == "no_post_t0"),
        "no_equity": sum(1 for r in recs if r.get("reason") == "no_equity"),
        "error": sum(1 for r in recs if r.get("reason") == "error"),
    }
    payload = {
        "full_universe": True,
        "labeling": "forward_only_loss_confirmed (Option B): first >dd_pct crater with "
                    "PnL-drop >= wd_ratio*equity-drop; withdrawal craters skip+reset peak",
        "t0_ms": T0_MS, "window_end_ms": WINDOW_END_MS,
        "dd_pct": DD_PCT, "recovery_frac": RECOVERY_FRAC,
        "recovery_horizon_ms": RECOVERY_HORIZON_MS,
        "peak_floor_usd": PEAK_FLOOR, "min_pre_t0_points": MIN_PRE_T0_POINTS,
        "withdrawal_ratio_floor": WITHDRAWAL_RATIO, "market_event_tau": MARKET_EVENT_TAU,
        "n_universe_fetched": len(recs),
        "n_qualified": len(members),
        "exclusions": exclusions,
        "withdrawal_accounting": withdrawal_accounting,
        "n_blowup": len(blowups), "n_stable": len(stable),
        "base_rate": len(blowups) / n_active,
        "effective_n_events": len({m["event_cluster"] for m in blowups if m["event_cluster"]}),
        "crash_day_histogram": dict(sorted(day_hist.items(), key=lambda kv: -kv[1])),
        "market_event_days": sorted(market_event_days),
        "n_idiosyncratic_blowups": len(idiosyncratic),
        "members": members,
    }
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"aggregated -> {OUT}")
    print(f"qualified={len(members)} blowup={len(blowups)} stable={len(stable)} "
          f"idiosyncratic={len(idiosyncratic)} eff_n={payload['effective_n_events']} "
          f"base_rate={payload['base_rate']:.3f}")
    print(f"withdrawal_accounting={withdrawal_accounting}")
    print(f"market_event_days={sorted(market_event_days)}")
    print(f"exclusions={exclusions}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--aggregate-only", action="store_true")
    a = p.parse_args()
    if a.aggregate_only:
        aggregate()
    else:
        run(limit=a.limit)
        aggregate()
