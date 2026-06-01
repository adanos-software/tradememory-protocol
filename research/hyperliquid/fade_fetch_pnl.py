"""FADE backtest — Stage A: refetch per-master TRADING PnL (pnlHistory).

The fade backtest must measure inverse-copy returns on a master's *trading* PnL,
NOT equity — equity is polluted by deposits/withdrawals (the exact confound that
broke the drift paper). cohort_behavioral.json only stored equity per bucket, so
we refetch `portfolio` (1 call/master) and keep perpAllTime pnlHistory +
accountValueHistory time series, keyed by address.

Safe rate (2.86 req/s, single light endpoint), checkpoint/resume, errors NOT
persisted (re-fetched on resume) — never lose a master.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "https://api.hyperliquid.xyz/info"
# Address source: cohort_stage1.json (3.4MB, light) — NOT the 926MB behavioral
# cohort. The fade signal is pnl-based, so we don't need behavioral primitives.
STAGE1 = Path("research/hyperliquid/cohort_stage1.json")
N_STABLE = 1500   # seed-fixed matched stable sample (blowups taken in full)
JSONL = Path("research/hyperliquid/fade_pnl.jsonl")
OUT = Path("research/hyperliquid/fade_pnl.json")
PROGRESS = Path("research/hyperliquid/_fade_pnl_progress.txt")

N_WORKERS = 8
MIN_INTERVAL = 0.35

_rate_lock = threading.Lock()
_next = [0.0]
_file_lock = threading.Lock()
_cnt = {"done": 0, "ok": 0, "err": 0}
_cnt_lock = threading.Lock()


def _gate():
    with _rate_lock:
        now = time.monotonic()
        slot = max(now, _next[0] + MIN_INTERVAL)
        _next[0] = slot
        wait = slot - now
    if wait > 0:
        time.sleep(wait)


def robust_post(body, max_retry=8):
    delay = 1.0
    for attempt in range(max_retry):
        _gate()
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
    raise RuntimeError("max retry")


def _series(port, period, key):
    by = {p[0]: p[1] for p in port}
    return [[int(t), float(v)] for t, v in by.get(period, {}).get(key, [])]


def fetch_one(addr):
    try:
        port = robust_post({"type": "portfolio", "user": addr})
    except Exception as e:  # noqa: BLE001
        return {"_err": True, "address": addr, "msg": str(e)[:100]}
    return {
        "address": addr,
        "pnl": _series(port, "perpAllTime", "pnlHistory"),
        "equity": _series(port, "perpAllTime", "accountValueHistory"),
    }


def _bump(ok):
    with _cnt_lock:
        _cnt["done"] += 1
        _cnt["ok" if ok else "err"] += 1


def main():
    s1 = json.loads(STAGE1.read_text(encoding="utf-8"))
    members = s1["members"]
    mev = set(s1.get("market_event_days", []))
    idio_blow = [m["address"] for m in members if m["label"] == "blowup"
                 and m.get("event_cluster") not in mev and m.get("blowup_time")]
    stable_pool = [m["address"] for m in members if m["label"] == "stable"
                   and m.get("n_eq_pre", 0) >= 2]
    stable = sorted(stable_pool, key=lambda a: hashlib.md5(a.encode()).hexdigest())[:N_STABLE]
    addrs = list(dict.fromkeys(idio_blow + stable))  # dedupe, preserve order
    print(f"fade pnl universe: {len(idio_blow)} idiosyncratic blowups + {len(stable)} stable = {len(addrs)}")
    done = set()
    if JSONL.exists():
        for ln in JSONL.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    r = json.loads(ln)
                    if not r.get("_err"):
                        done.add(r["address"])
                except Exception:  # noqa: BLE001
                    pass
    todo = [a for a in addrs if a not in done]
    print(f"cohort={len(addrs)} done={len(done)} todo={len(todo)}")
    start = time.time()
    if todo:
        with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
            futs = {ex.submit(fetch_one, a): a for a in todo}
            for i, fut in enumerate(as_completed(futs)):
                try:
                    rec = fut.result()
                except Exception as e:  # noqa: BLE001
                    rec = {"_err": True, "address": futs[fut], "msg": str(e)[:100]}
                ok = not rec.get("_err")
                if ok:
                    with _file_lock:
                        with open(JSONL, "a", encoding="utf-8") as f:
                            f.write(json.dumps(rec) + "\n")
                _bump(ok)
                if (i + 1) % 100 == 0:
                    el = time.time() - start
                    with _cnt_lock:
                        c = dict(_cnt)
                    PROGRESS.write_text(f"{c['done']}/{len(todo)} ok={c['ok']} err={c['err']} "
                                        f"{el:.0f}s {c['done']/el:.1f}/s\n")
    # aggregate JSONL -> dict
    data = {}
    for ln in JSONL.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            try:
                r = json.loads(ln)
                if not r.get("_err"):
                    data[r["address"]] = {"pnl": r["pnl"], "equity": r["equity"]}
            except Exception:  # noqa: BLE001
                pass
    OUT.write_text(json.dumps(data))
    print(f"aggregated {len(data)} masters -> {OUT} ({OUT.stat().st_size/1e6:.1f} MB)")
    PROGRESS.write_text(f"DONE {len(data)} masters in {time.time()-start:.0f}s\n")


if __name__ == "__main__":
    main()
