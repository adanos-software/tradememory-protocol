"""Plan 3 Stage 2 (SCALED / PROVISIONAL) — behavioral fetch → real tuning-split
anchors → provisional calibration → holdout detector demo.

Reads cohort_stage1.json (equity-labeled cohort), fetches full trajectory
(fills/orders/ledger) for a capped behavioral sub-cohort, computes each master's
per-bucket behavioral primitives, derives REAL tuning-split universe anchors
(median/MAD per primitive + Spearman cov), runs a provisional calibration with
those real anchors, and runs the frozen detector on a few held-out blow-up
masters to produce an INDICATIVE lead-time picture.

PROVISIONAL: capped sub-cohort, validation-style holdout (NOT the sealed locked
test). The full-universe pre-reg run + Part-2 lock + locked-test read are
human-gated (see Plan 3 plan Phases 7-8). Nothing here is a pre-registered number.
"""
from __future__ import annotations

import json
import time
import math
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from research.hyperliquid.normalize import order_events
from research.hyperliquid.trajectory import build_trajectory, meets_baseline
from research.hyperliquid.detector.bucketing import bucketize
from research.hyperliquid.detector.primitives import PrimitiveState
from research.hyperliquid.detector.config import AXES, PRIMITIVES, DetectorConfig, PrimitiveStats, BaselineStats
from research.hyperliquid.detector.calibration import run_calibration, baseline_from_anchors
from research.hyperliquid.detector.detector import run_detector

API = "https://api.hyperliquid.xyz/info"
STAGE1 = Path("research/hyperliquid/cohort_stage1.json")
OUT = Path("research/hyperliquid/plan3_provisional_results.json")
PROGRESS = Path("research/hyperliquid/_stage2_progress.txt")

T0_MS = int(datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
WINDOW_END_MS = int(datetime(2026, 4, 30, tzinfo=timezone.utc).timestamp() * 1000)
BUCKET_MS = 4 * 3600 * 1000
RATE_DELAY_S = 0.4
PRIM_ORDER = [p for a in AXES for p in PRIMITIVES[a]]

# Caps to keep the provisional run within ~20-30 min of fetching.
N_TUNING = 140      # tuning-split masters for universe anchors
N_HOLDOUT = 20      # test-split blow-up masters for the indicative detector demo


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
    raise RuntimeError("max retry")


def _split_bucket(addr):
    """Deterministic 40/20/40 tuning/val/test split by address."""
    h = int(__import__("hashlib").md5(addr.encode()).hexdigest(), 16) % 100
    return "tuning" if h < 40 else ("val" if h < 60 else "test")


def fetch_trajectory(addr):
    fills = robust_post({"type": "userFillsByTime", "user": addr, "startTime": 0, "aggregateByTime": False})
    time.sleep(RATE_DELAY_S)
    port = robust_post({"type": "portfolio", "user": addr})
    time.sleep(RATE_DELAY_S)
    led = robust_post({"type": "userNonFundingLedgerUpdates", "user": addr, "startTime": 0})
    time.sleep(RATE_DELAY_S)
    orders = robust_post({"type": "historicalOrders", "user": addr})
    time.sleep(RATE_DELAY_S)
    return build_trajectory(addr, fills, port, led, orders), orders


def coin_sigmas(traj):
    """Rough per-coin scale from fill-size dispersion (pooled fallback)."""
    by_coin = {}
    for tr in traj.trades:
        by_coin.setdefault(tr.coin, []).append(abs(tr.sz))
    sig = {}
    allsz = [abs(t.sz) for t in traj.trades] or [1.0]
    pooled = _mad(allsz) or 1.0
    for c, xs in by_coin.items():
        sig[c] = _mad(xs) or pooled
    return sig, pooled


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _mad(xs):
    if not xs:
        return 0.0
    m = _median(xs)
    return _median([abs(x - m) for x in xs])


def master_bucket_primitives(traj, orders, end_ms):
    """Run the master's history through bucketize+PrimitiveState, return the list
    of per-bucket 9-primitive dicts over [first_trade, end_ms)."""
    if not traj.trades:
        return []
    origin = traj.trades[0].time
    if origin >= end_ms:
        return []
    oe = order_events(orders)
    buckets = bucketize(traj, origin, end_ms, BUCKET_MS, orders=oe)
    cs, pooled = coin_sigmas(traj)
    st = PrimitiveState(coin_sigma=cs, pooled_sigma=pooled)
    return [st.bucket_values(b) for b in buckets]


def _spearman_rank(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    rank = [0.0] * len(values)
    for r, i in enumerate(order):
        rank[i] = r
    return rank


def spearman_cov(series_by_prim):
    """Spearman correlation matrix (dict[p][q]) over pooled bucket-values."""
    ranks = {p: _spearman_rank(series_by_prim[p]) for p in PRIM_ORDER}
    cov = {}
    for p in PRIM_ORDER:
        cov[p] = {}
        rp = ranks[p]
        mp = sum(rp) / len(rp) if rp else 0.0
        for q in PRIM_ORDER:
            rq = ranks[q]
            mq = sum(rq) / len(rq) if rq else 0.0
            num = sum((rp[i] - mp) * (rq[i] - mq) for i in range(len(rp)))
            dp = math.sqrt(sum((x - mp) ** 2 for x in rp))
            dq = math.sqrt(sum((x - mq) ** 2 for x in rq))
            cov[p][q] = (num / (dp * dq)) if dp > 0 and dq > 0 else (1.0 if p == q else 0.0)
    return cov


def main():
    data = json.loads(STAGE1.read_text())
    members = data["members"]
    market_event_days = set(data.get("market_event_days", []))

    # behavioral cohort: prefer idiosyncratic blow-ups + stable, with pre-T0 equity
    def has_pre(m):
        return m.get("n_eq_pre", 0) >= 2 and m.get("pre_t0_peak")
    tuning = [m for m in members if _split_bucket(m["address"]) == "tuning" and has_pre(m)][:N_TUNING]
    test_blow = [m for m in members if _split_bucket(m["address"]) == "test"
                 and m["label"] == "blowup" and m["event_cluster"] not in market_event_days
                 and has_pre(m)][:N_HOLDOUT]

    pooled_series = {p: [] for p in PRIM_ORDER}
    n_included = 0
    n_fetch = 0
    start = time.time()

    for i, m in enumerate(tuning):
        try:
            traj, orders = fetch_trajectory(m["address"])
            n_fetch += 1
            if not meets_baseline(traj, T0_MS, 50, 14.0):
                continue
            # universe anchors from PRE-T0 buckets (outcome-blind baseline window)
            bvals = master_bucket_primitives(traj, orders, T0_MS)
            if not bvals:
                continue
            for bv in bvals:
                for p in PRIM_ORDER:
                    pooled_series[p].append(bv[p])
            n_included += 1
        except Exception:
            pass
        if (i + 1) % 10 == 0:
            PROGRESS.write_text(f"tuning {i+1}/{len(tuning)} | included={n_included} | {time.time()-start:.0f}s\n")

    # Real universe anchors
    anchors = {a: {p: {"median": _median(pooled_series[p]), "mad": (_mad(pooled_series[p]) or 1e-6)}
                   for p in PRIMITIVES[a]} for a in AXES}
    cov = spearman_cov(pooled_series) if all(pooled_series[p] for p in PRIM_ORDER) else \
          {p: {q: (1.0 if p == q else 0.0) for q in PRIM_ORDER} for p in PRIM_ORDER}

    # Provisional calibration with REAL anchors (small grid for speed)
    cal = run_calibration(
        anchors, cov, seed=7,
        out_path="research/hyperliquid/calibration_result_realsplit_provisional.json",
        n_streams=200,
        bucket_ms_options=(BUCKET_MS,),
        M_options=(2, 3, 4, 6),
        tau_options=(0.3,),
        weights_options=("equal",),
        kappa_options=(14,),
    )
    win = cal["winning_tuple"]

    # Holdout indicative detector demo on test-split idiosyncratic blow-ups
    universe = {a: {p: PrimitiveStats(anchors[a][p]["median"], anchors[a][p]["mad"], 9999)
                    for p in PRIMITIVES[a]} for a in AXES}
    cfg = DetectorConfig(bucket_ms=BUCKET_MS, M=win["M"],
                         tau={a: win["tau"] for a in AXES},
                         weights={a: {p: 1/3 for p in PRIMITIVES[a]} for a in AXES},
                         kappa=win["kappa"], burn_in=20)
    holdout = []
    for m in test_blow:
        try:
            traj, orders = fetch_trajectory(m["address"])
            if not meets_baseline(traj, T0_MS, 50, 14.0):
                continue
            # self stats from this master's own pre-T0 buckets
            pre = master_bucket_primitives(traj, orders, T0_MS)
            if not pre:
                continue
            self_stats = {a: {p: PrimitiveStats(_median([b[p] for b in pre]),
                                                _mad([b[p] for b in pre]) or 1e-6, len(pre))
                              for p in PRIMITIVES[a]} for a in AXES}
            baseline = BaselineStats(self_stats, universe)
            first_liq = next((t.time for t in sorted(traj.trades, key=lambda x: x.time) if t.is_liquidation), None)
            recs = run_detector(traj, baseline, cfg, origin_ms=T0_MS, end_ms=WINDOW_END_MS,
                                coin_sigma=coin_sigmas(traj)[0], pooled_sigma=coin_sigmas(traj)[1],
                                first_liq_ms=first_liq, orders=order_events(orders))
            alert = next((r for r in recs if r.alert_raised and r.is_early), None)
            blow = m["blowup_time"]
            lead_h = ((blow - alert.bucket_end_ms) / 3_600_000) if (alert and blow) else None
            holdout.append({"address": m["address"], "blowup_time": blow,
                            "alerted_early": alert is not None,
                            "carrying_axis": alert.carrying_axis if alert else None,
                            "lead_time_hours": lead_h})
        except Exception:
            pass

    alerted = [h for h in holdout if h["alerted_early"]]
    leads = [h["lead_time_hours"] for h in alerted if h["lead_time_hours"] is not None]
    payload = {
        "scaled_provisional": True,
        "tuning_masters_fetched": n_fetch, "tuning_masters_included": n_included,
        "real_anchors": anchors,
        "provisional_winner": win,
        "typeI_target_relaxed": cal["typeI_target_relaxed"],
        "holdout_n": len(holdout), "holdout_alerted_early": len(alerted),
        "holdout_median_lead_hours": (_median(leads) if leads else None),
        "holdout": holdout,
    }
    OUT.write_text(json.dumps(payload, indent=2))
    PROGRESS.write_text(
        f"DONE in {time.time()-start:.0f}s | tuning_incl={n_included} | "
        f"holdout {len(alerted)}/{len(holdout)} early | "
        f"median_lead_h={payload['holdout_median_lead_hours']}\n")
    print(PROGRESS.read_text())


if __name__ == "__main__":
    main()
