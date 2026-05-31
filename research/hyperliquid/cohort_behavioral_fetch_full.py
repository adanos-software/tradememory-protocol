"""Full-universe Stage-2 behavioral fetch — the PRE-REGISTERED run.

Generalizes `cohort_behavioral_fetch.py` from the capped scaled sub-cohort to the
full pre-registered cohort: ALL idiosyncratic blow-ups (no cap — they are the
precious events; no sampling bias on the blow-up class) plus a SEED-FIXED matched
stable sample (default 1:1 by count). For each master we fetch the full trajectory
(fills / orders / ledger / portfolio), bucket it (4h), and store the per-bucket
behavioral primitives so the experiment runner replays A/B/ablation without
re-fetching.

Robustness (multi-thousand-master, multi-hour run):
  * concurrent workers + single global rate gate (requests spaced >= MIN_INTERVAL),
  * robust 429 backoff,
  * per-master JSONL checkpoint (resume skips finished masters),
  * floats rounded (6 sig-decimals / equity 2dp) to keep the JSON loadable.

Output cohort_behavioral.json keeps the SAME schema the downstream readers expect
(fair_comparison.py / experiment_run.py / paper/make_figures.py): masters[] with
address, label, split, blowup_time, event_cluster, first_liq_ms, n_buckets, series.

CLI:
  python research/hyperliquid/cohort_behavioral_fetch_full.py
  python research/hyperliquid/cohort_behavioral_fetch_full.py --max-blowup 1500 --stable-ratio 1.0
  python research/hyperliquid/cohort_behavioral_fetch_full.py --aggregate-only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from research.hyperliquid.trajectory import build_trajectory
from research.hyperliquid.stage2_behavioral import coin_sigmas, _split_bucket
from research.hyperliquid.detector.bucketing import bucketize
from research.hyperliquid.detector.primitives import PrimitiveState
from research.hyperliquid.normalize import order_events

API = "https://api.hyperliquid.xyz/info"
STAGE1 = Path("research/hyperliquid/cohort_stage1.json")
JSONL = Path("research/hyperliquid/cohort_behavioral_full.jsonl")
OUT = Path("research/hyperliquid/cohort_behavioral.json")
PROGRESS = Path("research/hyperliquid/_behavioral_progress.txt")

T0_MS = int(datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
WINDOW_END_MS = int(datetime(2026, 4, 30, tzinfo=timezone.utc).timestamp() * 1000)
BUCKET_MS = 4 * 3600 * 1000

N_WORKERS = 6                # heavy endpoints (userFillsByTime) are weight-limited
MIN_INTERVAL = 0.5           # ~2 req/s global; 429 errors are NOT persisted (re-fetched
                             # on resume) so transient rate-limits never lose a master
STABLE_RATIO_DEFAULT = 1.0   # matched stable sample size = ratio * n_idiosyncratic_blowup

_rate_lock = threading.Lock()
_next_slot = [0.0]
_file_lock = threading.Lock()
_counter_lock = threading.Lock()
_stats = {"done": 0, "kept": 0, "blowup": 0, "stable": 0, "errors": 0, "empty": 0}


def _rate_gate():
    with _rate_lock:
        now = time.monotonic()
        slot = max(now, _next_slot[0] + MIN_INTERVAL)
        _next_slot[0] = slot
        wait = slot - now
    if wait > 0:
        time.sleep(wait)


def robust_post(body, max_retry=9):
    delay = 1.0
    for attempt in range(max_retry):
        _rate_gate()
        try:
            req = urllib.request.Request(
                API, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "tm-research/0.1"})
            with urllib.request.urlopen(req, timeout=60) as r:
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


def _fetch_trajectory(addr):
    fills = robust_post({"type": "userFillsByTime", "user": addr, "startTime": 0, "aggregateByTime": False})
    port = robust_post({"type": "portfolio", "user": addr})
    led = robust_post({"type": "userNonFundingLedgerUpdates", "user": addr, "startTime": 0})
    orders = robust_post({"type": "historicalOrders", "user": addr})
    return build_trajectory(addr, fills, port, led, orders), orders


def _r(x, nd=6):
    return round(x, nd) if isinstance(x, (int, float)) else x


def fetch_master(m):
    """Fetch + bucket one master. Returns a record dict, or {'_skip': reason}."""
    try:
        traj, orders = _fetch_trajectory(m["address"])
    except Exception as e:  # noqa: BLE001
        return {"_skip": "error", "address": m["address"], "err": str(e)[:120]}
    if not traj.trades:
        return {"_skip": "empty", "address": m["address"]}
    origin = max(traj.trades[0].time, T0_MS)
    end = m["blowup_time"] if m.get("blowup_time") else WINDOW_END_MS
    if origin >= end:
        return {"_skip": "empty", "address": m["address"]}
    oe = order_events(orders)
    buckets = bucketize(traj, origin, end, BUCKET_MS, orders=oe)
    cs, pooled = coin_sigmas(traj)
    st = PrimitiveState(coin_sigma=cs, pooled_sigma=pooled)
    series = []
    for b in buckets:
        pv = st.bucket_values(b)
        series.append({
            "prim": {k: _r(v) for k, v in pv.items()},
            "equity": _r(b.equity_end, 2),
            "end_ms": b.end_ms,
        })
    first_liq = next((t.time for t in sorted(traj.trades, key=lambda x: x.time)
                      if t.is_liquidation), None)
    return {
        "address": m["address"],
        "label": m["label"],
        "split": _split_bucket(m["address"]),
        "blowup_time": m.get("blowup_time"),
        "event_cluster": m.get("event_cluster"),
        "first_liq_ms": first_liq,
        "n_buckets": len(series),
        "series": series,
    }


def _bump(rec):
    with _counter_lock:
        _stats["done"] += 1
        if "_skip" in rec:
            _stats["errors" if rec["_skip"] == "error" else "empty"] += 1
        else:
            _stats["kept"] += 1
            _stats[rec["label"]] += 1


def _append(rec):
    with _file_lock:
        with open(JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


def _write_progress(total, start):
    with _counter_lock:
        s = dict(_stats)
    el = time.time() - start
    rate = s["done"] / el if el > 0 else 0
    eta = (total - s["done"]) / rate / 60 if rate > 0 else 0
    PROGRESS.write_text(
        f"{s['done']}/{total} | kept={s['kept']} (blowup={s['blowup']} stable={s['stable']}) "
        f"empty={s['empty']} err={s['errors']} | {el:.0f}s {rate:.1f}/s ETA~{eta:.0f}m\n")


def _build_cohort(max_blowup, stable_ratio):
    data = json.loads(STAGE1.read_text())
    members = data["members"]
    mev = set(data.get("market_event_days", []))
    idio_blow = [m for m in members if m["label"] == "blowup"
                 and m.get("event_cluster") not in mev and m.get("blowup_time")]
    # Deterministic order for reproducibility / stable resume.
    idio_blow.sort(key=lambda m: m["address"])
    if max_blowup and len(idio_blow) > max_blowup:
        # seed-fixed sub-sample (hash order) if a cap is requested
        idio_blow = sorted(idio_blow, key=lambda m: hashlib.md5(m["address"].encode()).hexdigest())[:max_blowup]
    stable_pool = [m for m in members if m["label"] == "stable" and m.get("n_eq_pre", 0) >= 2]
    n_stable = min(len(stable_pool), round(stable_ratio * len(idio_blow)))
    stable_sample = sorted(stable_pool, key=lambda m: hashlib.md5(m["address"].encode()).hexdigest())[:n_stable]
    cohort = idio_blow + stable_sample
    return cohort, len(idio_blow), len(stable_sample), len(stable_pool)


def run(max_blowup=None, stable_ratio=STABLE_RATIO_DEFAULT):
    cohort, n_blow, n_stab, n_stab_pool = _build_cohort(max_blowup, stable_ratio)
    print(f"cohort: {n_blow} idiosyncratic blowups + {n_stab} stable "
          f"(matched {stable_ratio}x, pool {n_stab_pool}) = {len(cohort)}")
    done = set()
    if JSONL.exists():
        for ln in JSONL.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                rec = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if rec.get("_skip") == "error":
                continue  # stale error records -> re-fetch on resume (never skip a master)
            done.add(rec["address"])
            _bump(rec)  # re-seed counters from prior successful work
    todo = [m for m in cohort if m["address"] not in done]
    print(f"already_done={len(done)} todo={len(todo)} workers={N_WORKERS} interval={MIN_INTERVAL}s")
    start = time.time()
    if not todo:
        print("nothing to fetch; all cohort masters already fetched")
        return
    with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
        futs = {ex.submit(fetch_master, m): m for m in todo}
        for i, fut in enumerate(as_completed(futs)):
            try:
                rec = fut.result()
            except Exception as e:  # noqa: BLE001
                rec = {"_skip": "error", "address": futs[fut]["address"], "err": str(e)[:120]}
            # Persist successes + genuine empties; DROP transient errors (429) so the
            # next resume re-fetches them — never lose a master to a rate-limit blip.
            if rec.get("_skip") != "error":
                _append(rec)
            _bump(rec)
            if (i + 1) % 50 == 0:
                _write_progress(len(cohort), start)
    _write_progress(len(cohort), start)
    print("fetch complete:", PROGRESS.read_text().strip())


def aggregate():
    if not JSONL.exists():
        print("no JSONL to aggregate", file=sys.stderr)
        return
    masters = []
    for ln in JSONL.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            try:
                rec = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if "_skip" not in rec:
                masters.append(rec)
    payload = {
        "full_universe": True,
        "t0_ms": T0_MS, "window_end_ms": WINDOW_END_MS, "bucket_ms": BUCKET_MS,
        "n_blowup": sum(1 for m in masters if m["label"] == "blowup"),
        "n_stable": sum(1 for m in masters if m["label"] == "stable"),
        "splits": {s: sum(1 for m in masters if m["split"] == s) for s in ("tuning", "val", "test")},
        "masters": masters,
    }
    OUT.write_text(json.dumps(payload))
    sz = OUT.stat().st_size / 1e6
    print(f"aggregated -> {OUT} ({sz:.1f} MB)")
    print(f"masters={len(masters)} blowup={payload['n_blowup']} stable={payload['n_stable']} "
          f"splits={payload['splits']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--max-blowup", type=int, default=None)
    p.add_argument("--stable-ratio", type=float, default=STABLE_RATIO_DEFAULT)
    p.add_argument("--aggregate-only", action="store_true")
    a = p.parse_args()
    if a.aggregate_only:
        aggregate()
    else:
        run(max_blowup=a.max_blowup, stable_ratio=a.stable_ratio)
        aggregate()
