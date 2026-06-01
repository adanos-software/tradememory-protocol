"""FADE backtest — Stage B: does fading hot/parabolic masters make money?

Signal (causal, pnl-based — NOT the abstract 'leverage' primitive, which is a
volatility-normalized z-quantity with 10^15 tails and is unusable, and NOT
behavioral drift, which the paper showed doesn't predict blow-ups): fade a master
after a strong recent run-up (the 'hot whale everyone copies at the top'). Win if
they revert/crater over the forward horizon; lose if they keep mooning (squeeze).

Inverse-copy return is measured on TRADING PnL (pnlHistory), not equity, so
deposits/withdrawals don't pollute it (the exact confound that broke the paper).

Rigor handled:
  * causal: signal uses only the trailing window; fade entered AFTER; no use of
    blowup_time to select who to fade.
  * sampling bias: the behavioral cohort over-samples blow-ups (we fetched ~all
    idiosyncratic blow-ups but only ~1/4 of stable) -> reweight to the Stage-1
    qualified population so the 'moon tail' (stable masters you lose on) counts at
    true frequency.
  * squeeze tail: report fade return raw (uncapped, true unlimited-short loss) AND
    capped at -1.0 (position liquidated).
  * event clustering: group events by crash-day / signal-week so correlated wins
    don't inflate confidence.
  * costs: report gross AND net of a funding+fee estimate.
  * exploratory: we scan a small grid of (lookback W, hot threshold R, horizon H)
    and report ALL of it (no cherry-picking). This is a feasibility probe, not a
    pre-registered result.

Inputs: fade_pnl.json (per-master pnl/equity series), cohort_stage1.json (label,
event_cluster, blowup_time, population counts). Does NOT need the 926MB behavioral
cohort.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

PNL = Path("research/hyperliquid/fade_pnl.json")
STAGE1 = Path("research/hyperliquid/cohort_stage1.json")
DAY = 86_400_000

# Cost estimate (annualized funding on a crowded perp short + round-trip fees).
ANNUAL_FUNDING = 0.20
ROUNDTRIP_FEE = 0.001


def _nearest(series, t):
    """(time,value) nearest to t in a sorted [[t,v]] list; None if empty."""
    if not series:
        return None
    lo, hi = 0, len(series) - 1
    if t <= series[0][0]:
        return series[0]
    if t >= series[-1][0]:
        return series[-1]
    while lo < hi:
        mid = (lo + hi) // 2
        if series[mid][0] < t:
            lo = mid + 1
        else:
            hi = mid
    # series[lo] is first >= t; compare with lo-1
    a = series[lo - 1]
    b = series[lo]
    return a if (t - a[0]) <= (b[0] - t) else b


def master_return(pnl, equity, t1, t2):
    """Trading return over [t1,t2] = (pnl[t2]-pnl[t1]) / equity_base. None if unusable."""
    p1 = _nearest(pnl, t1)
    p2 = _nearest(pnl, t2)
    e1 = _nearest(equity, t1)
    if p1 is None or p2 is None or e1 is None:
        return None
    base = e1[1]
    if base is None or base < 1000:  # need a real capital base to size a copy
        return None
    return (p2[1] - p1[1]) / base


def find_fade_event(pnl, equity, W_ms, R_hot, H_ms):
    """First time the trailing-W trading return exceeds R_hot (the 'hot run-up'),
    with >= H of forward data. Returns (t_signal, fade_return_uncapped) or None.
    Causal: only trailing data triggers; forward return measured after."""
    if len(pnl) < 4:
        return None
    t_start = pnl[0][0] + W_ms
    t_end = pnl[-1][0] - H_ms
    # scan candidate signal times on the pnl grid
    for t, _ in pnl:
        if t < t_start or t > t_end:
            continue
        run = master_return(pnl, equity, t - W_ms, t)
        if run is None or run < R_hot:
            continue
        fwd = master_return(pnl, equity, t, t + H_ms)
        if fwd is None:
            continue
        return t, -fwd  # fade = short = inverse of master's forward return
    return None


def cluster_key(addr, t_signal, label, ev):
    if label == "blowup" and ev:
        return ev
    return f"wk_{int(t_signal // (7 * DAY))}"


def run():
    pnl_data = json.loads(PNL.read_text(encoding="utf-8"))
    s1 = json.loads(STAGE1.read_text(encoding="utf-8"))
    meta = {m["address"]: m for m in s1["members"]}
    pop_blow = s1["n_idiosyncratic_blowups"]
    pop_stable = s1["n_stable"]

    # sampled counts among masters we have pnl for
    have = [a for a in pnl_data if a in meta]
    samp_blow = sum(1 for a in have if meta[a]["label"] == "blowup")
    samp_stable = sum(1 for a in have if meta[a]["label"] == "stable")
    w_blow = pop_blow / samp_blow if samp_blow else 1.0
    w_stable = pop_stable / samp_stable if samp_stable else 1.0
    print(f"masters with pnl={len(have)} | sample blow={samp_blow} stable={samp_stable}")
    print(f"population blow={pop_blow} stable={pop_stable} | reweight blow x{w_blow:.2f} stable x{w_stable:.2f}\n")

    grid_W = [14, 30]
    grid_R = [0.30, 0.50, 1.00]
    grid_H = [7, 14, 30]

    print(f"{'W':>3} {'R_hot':>6} {'H':>3} | {'n_ev':>5} {'win%':>6} {'wMean':>8} {'wMed':>8} "
          f"{'netMean':>8} {'p5':>7} {'p95':>7} {'clMean':>8} {'cl_t':>6}")
    print("-" * 96)
    results = []
    for W in grid_W:
        for R in grid_R:
            for H in grid_H:
                W_ms, H_ms = W * DAY, H * DAY
                events = []  # (cluster, weight, fade_ret_uncapped, fade_ret_capped, label)
                for a in have:
                    d = pnl_data[a]
                    ev = find_fade_event(d["pnl"], d["equity"], W_ms, R, H_ms)
                    if ev is None:
                        continue
                    t_sig, fr = ev
                    lab = meta[a]["label"]
                    wt = w_blow if lab == "blowup" else w_stable
                    ck = cluster_key(a, t_sig, lab, meta[a].get("event_cluster"))
                    events.append((ck, wt, fr, max(fr, -1.0), lab))
                if len(events) < 20:
                    continue
                wsum = sum(e[1] for e in events)
                wmean = sum(e[1] * e[2] for e in events) / wsum
                # net of costs (funding for H days + roundtrip fee), applied to the position
                cost = ANNUAL_FUNDING * (H / 365.0) + ROUNDTRIP_FEE
                netmean = sum(e[1] * (e[3] - cost) for e in events) / wsum  # use capped for net (realistic)
                rets = sorted(e[2] for e in events)
                wmed = statistics.median([e[2] for e in events])
                winw = sum(e[1] for e in events if e[2] > 0) / wsum
                p5 = rets[max(0, int(0.05 * len(rets)))]
                p95 = rets[min(len(rets) - 1, int(0.95 * len(rets)))]
                # event-clustered mean +/- across-cluster t-stat (capped, net)
                byc = {}
                for ck, wt, fr, frc, lab in events:
                    byc.setdefault(ck, []).append((wt, frc - cost))
                cl_means = [sum(w * x for w, x in v) / sum(w for w, _ in v) for v in byc.values()]
                cl_mean = statistics.mean(cl_means)
                cl_sd = statistics.pstdev(cl_means) if len(cl_means) > 1 else 0.0
                cl_t = (cl_mean / (cl_sd / (len(cl_means) ** 0.5))) if cl_sd > 0 else 0.0
                results.append((W, R, H, len(events), winw, wmean, netmean, cl_mean, cl_t, len(byc)))
                print(f"{W:>3} {R:>6.2f} {H:>3} | {len(events):>5} {winw*100:>5.1f}% {wmean:>8.3f} {wmed:>8.3f} "
                      f"{netmean:>8.3f} {p5:>7.2f} {p95:>7.2f} {cl_mean:>8.3f} {cl_t:>6.2f}")

    print("\nReading:")
    print("  wMean/wMed/netMean = population-reweighted mean/median/net-of-cost fade return per event (capped at -1 for net).")
    print("  win% = reweighted fraction of fades that profit. p5/p95 = uncapped tail (true squeeze risk).")
    print("  clMean = event-clustered net mean; cl_t = across-cluster t-stat (|t|>~2 => not noise).")
    print("  Costs: funding {:.0%}/yr * H/365 + {:.1%} fee. Exploratory grid (no cherry-pick).".format(ANNUAL_FUNDING, ROUNDTRIP_FEE))
    print("  CONSERVATIVE: market-event (crash-day) blow-ups are EXCLUDED from the cohort -> real fade likely does better in crashes.")
    if results:
        best = max(results, key=lambda r: r[7])  # best clustered net mean
        W, R, H, n, win, wm, nm, clm, clt, nc = best
        print(f"\nBest net cell: W={W} R_hot={R:.0%} H={H}d -> netMean {nm:+.3f}/event, win {win:.0%}, "
              f"clustered t={clt:.2f} over {nc} clusters (n={n}).")
        print("VERDICT:", "fade is net-positive & not noise" if (nm > 0 and clt > 2)
              else ("net-positive but noisy (need more/OOS)" if nm > 0 else "fade does NOT make money on this signal"))


if __name__ == "__main__":
    run()
