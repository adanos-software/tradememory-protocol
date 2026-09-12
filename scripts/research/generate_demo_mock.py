"""
Generate dashboard demo mock JSON files from a synthetic, internally-consistent
trade sequence.

WHY THIS EXISTS
---------------
The previous mock set (generate_backtest_mock.py, sourced from data/backtest_v1.db)
shipped numbers that do not survive inspection:

  * cumulative PnL reached -29,488 against a stated 10,000 account
    -> 16 points on the equity curve had equity <= 0 (the account was bust)
  * Overview reported max_drawdown_pct 0.4066 while the equity series' own
    drawdown_pct field peaked at 0.7013
  * Overview reported 10,169 trades while the chart's trade counter, and the sum
    of the three strategy files, both ended at 4,102
  * strategy-im and strategy-pb reported the same session as both best and worst
  * every trade risked a flat $100, so total PnL 276,535 = +2,765R over 4,102
    trades = +0.68R per trade. R-multiples are scale-invariant, so no choice of
    account size hides an expectancy roughly 10x anything a real intraday system
    produces.

This generator replaces that set. Everything below is DERIVED from one simulated
trade list, so the aggregates cannot contradict the series they summarise.

WHAT THIS DATA IS
-----------------
Synthetic. It is an interface preview, not a backtest and not live results. The
disclaimer written into the JSON says exactly that. Do not present these figures
as evidence of performance.

Capital frame (stated, not implied):
    account          $100,000
    risk per trade   $250 (0.25%)  -> 1R = $250
    period           2024-01-02 .. 2026-02-25 (~26 months)
    trades           ~640 (~1.2 per trading day; a selective intraday system)

Target profile, chosen to be unremarkable on purpose:
    total return     ~ +18%
    profit factor    ~ 1.20
    win rate         ~ 0.45
    max drawdown     ~ 6-14% (emergent; the seed is chosen so it lands in band)

Usage:
    python scripts/research/generate_demo_mock.py [--seed N] [--check]

--check re-reads what it wrote and asserts cross-file consistency.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MOCK_DIR = ROOT / "dashboard" / "src" / "mock"

# ── frame ──────────────────────────────────────────────────────────────
ACCOUNT = 100_000.0
R_DOLLARS = 250.0
START = datetime(2024, 1, 2, tzinfo=timezone.utc)
END = datetime(2026, 2, 25, tzinfo=timezone.utc)

DISCLAIMER = (
    "⚠️ Illustrative demo dataset. Synthetic trades generated for "
    "interface preview only - not a backtest, not live trading results. "
    "Account $100,000, risk $250/trade (1R)."
)

SESSIONS = ["Asia", "London", "NY"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

# name -> (slug, n_trades, win_rate, win_mean_r, win_sd, loss_mean_r, loss_sd,
#          baseline_pf, baseline_wr, session_bias, avg_hold_s)
# session_bias nudges R by session so the heatmap tells a story the product is
# meant to find ("this strategy earns in London, bleeds in Asia").
STRATEGY_SPEC = {
    "IntradayMomentum": dict(
        slug="im", n=320, wr=0.46, win_mu=1.55, win_sd=0.85,
        loss_mu=-1.02, loss_sd=0.22, baseline_pf=1.34, baseline_wr=0.48,
        bias={"London": 0.10, "NY": 0.02, "Asia": -0.12}, hold=5143,
        symbols=["EURUSD", "GBPUSD"],
    ),
    "VolBreakout": dict(
        slug="vb", n=220, wr=0.43, win_mu=1.40, win_sd=0.78,
        loss_mu=-1.00, loss_sd=0.20, baseline_pf=1.17, baseline_wr=0.45,
        bias={"London": 0.06, "NY": 0.04, "Asia": -0.16}, hold=2019,
        symbols=["XAUUSD", "EURUSD"],
    ),
    # n kept at 150+ deliberately: at n=100 the sampling noise on the smallest
    # strategy threw PF to 1.75, which reads as the one "too good" tile on the
    # board and pulls attention to the wrong thing.
    "PullbackEntry": dict(
        slug="pb", n=150, wr=0.47, win_mu=1.36, win_sd=0.70,
        loss_mu=-1.05, loss_sd=0.24, baseline_pf=1.24, baseline_wr=0.49,
        bias={"London": 0.04, "NY": 0.09, "Asia": -0.08}, hold=3229,
        symbols=["XAUUSD", "GBPUSD"],
    ),
}
DISPLAY = {"IntradayMomentum": "IntradayMomentum", "VolBreakout": "VolBreakout",
           "PullbackEntry": "Pullback"}

SESSION_HOUR = {"Asia": 3, "London": 9, "NY": 15}


# ── helpers ────────────────────────────────────────────────────────────
def trading_days() -> list[datetime]:
    days, d = [], START
    while d <= END:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def pf_of(rs: list[float]) -> float:
    gp = sum(r for r in rs if r > 0)
    gl = abs(sum(r for r in rs if r < 0))
    if gl == 0:
        return 999.0 if gp > 0 else 0.0
    return round(gp / gl, 2)


def wr_of(rs: list[float]) -> float:
    return round(sum(1 for r in rs if r > 0) / len(rs), 3) if rs else 0.0


def max_dd(equity: list[float]) -> float:
    peak, worst = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        if peak > 0:
            worst = max(worst, (peak - e) / peak)
    return worst


# ── simulation ─────────────────────────────────────────────────────────
def regime_series(rng: random.Random, n_weeks: int) -> list[float]:
    """Slow mean-reverting latent state, roughly in [-1, 1].

    Without this every strategy performs identically all the way through and the
    equity curve comes out implausibly smooth (MDD ~4% across 80 seeds). Real
    systems run hot and cold in stretches, and the whole point of the Beliefs /
    rolling-metrics views is to show that happening.
    """
    z, out = 0.0, []
    for _ in range(n_weeks):
        z = 0.88 * z + rng.gauss(0, 0.46)
        out.append(max(-1.0, min(1.0, z)))
    return out


def simulate(rng: random.Random) -> list[dict]:
    days = trading_days()
    week0 = START - timedelta(days=START.weekday())
    n_weeks = ((END - week0).days // 7) + 2
    regimes = {n: regime_series(rng, n_weeks) for n in STRATEGY_SPEC}
    trades: list[dict] = []

    for name, spec in STRATEGY_SPEC.items():
        picked = rng.sample(days, spec["n"]) if spec["n"] <= len(days) else \
            [rng.choice(days) for _ in range(spec["n"])]
        for i, day in enumerate(sorted(picked)):
            session = rng.choices(SESSIONS, weights=[0.28, 0.42, 0.30])[0]
            bias = spec["bias"][session]
            z = regimes[name][(day - week0).days // 7]
            # bias shifts the odds of a win slightly, not the payoff, so the
            # session story shows up the way a real edge would; z adds the
            # hot/cold stretches that give the curve its drawdowns.
            win = rng.random() < min(0.92, max(0.05,
                                               spec["wr"] + bias + 0.11 * z))
            if win:
                r = rng.gauss(spec["win_mu"], spec["win_sd"])
                r = min(6.0, max(0.05, r))
            else:
                r = rng.gauss(spec["loss_mu"], spec["loss_sd"])
                r = max(-3.5, min(-0.05, r))
            hold = max(60, int(rng.gauss(spec["hold"], spec["hold"] * 0.45)))
            ts = day.replace(hour=SESSION_HOUR[session],
                             minute=rng.randrange(0, 60))
            sym = rng.choice(spec["symbols"])
            # entry confidence is mildly predictive: that is the product claim,
            # and a flat 0.5 (as in the old mock) would make the calibration
            # chart meaningless.
            conf = min(0.95, max(0.05,
                                 rng.gauss(0.55 + 0.06 * r, 0.16)))
            trades.append({
                "id": f"DEMO-{spec['slug'].upper()}_{sym}_BUY-{i:04d}",
                "strategy": name,
                "ts": ts,
                "date": ts.strftime("%Y-%m-%d"),
                "side": "BUY",
                "pnl_r": round(r, 2),
                "pnl": round(r * R_DOLLARS, 2),
                "session": session,
                "day": DAYS[ts.weekday()],
                "hold_seconds": hold,
                "confidence": round(conf, 2),
                "symbol": sym,
            })

    trades.sort(key=lambda t: t["ts"])
    return trades


# ── file generators ────────────────────────────────────────────────────
def gen_overview(trades: list[dict], mdd: float) -> dict:
    rs = [t["pnl_r"] for t in trades]
    total_pnl = round(sum(t["pnl"] for t in trades), 2)
    return {
        "_disclaimer": DISCLAIMER,
        "total_trades": len(trades),
        "total_pnl": total_pnl,
        "win_rate": wr_of(rs),
        "profit_factor": pf_of(rs),
        "current_equity": round(ACCOUNT + total_pnl, 2),
        "max_drawdown_pct": round(mdd, 4),
        # one episodic memory per trade, plus the semantic / procedural /
        # affective rows the other layers write.
        "memory_count": len(trades) + 213,
        "avg_confidence": round(sum(t["confidence"] for t in trades) / len(trades), 3),
        "last_trade_date": trades[-1]["ts"].isoformat(),
        "strategies": [DISPLAY[s] for s in STRATEGY_SPEC],
    }


def gen_equity(trades: list[dict]) -> tuple[list[dict], float]:
    by_day: dict[str, list[dict]] = {}
    for t in trades:
        by_day.setdefault(t["date"], []).append(t)

    out, cum, n, peak = [], 0.0, 0, ACCOUNT
    for date in sorted(by_day):
        for t in by_day[date]:
            cum += t["pnl"]
            n += 1
        equity = ACCOUNT + cum
        peak = max(peak, equity)
        out.append({
            "date": date,
            "cumulative_pnl": round(cum, 2),
            # real drawdown against peak equity, including while under water.
            "drawdown_pct": round((peak - equity) / peak, 4),
            "trade_count": n,
        })
    return out, max(p["drawdown_pct"] for p in out)


def gen_rolling(trades: list[dict], window: int = 20) -> list[dict]:
    out = []
    for i in range(window, len(trades) + 1, 6):
        chunk = trades[i - window:i]
        rs = [t["pnl_r"] for t in chunk]
        out.append({
            "date": chunk[-1]["date"],
            "rolling_pf": pf_of(rs),
            "rolling_wr": wr_of(rs),
            "rolling_avg_r": round(sum(rs) / len(rs), 2),
            "window_size": window,
        })
    return out


def _weeks(trades: list[dict]) -> list[tuple[str, list[dict]]]:
    buckets: dict[str, list[dict]] = {}
    for t in trades:
        monday = (t["ts"] - timedelta(days=t["ts"].weekday())).strftime("%Y-%m-%d")
        buckets.setdefault(monday, []).append(t)
    return sorted(buckets.items())


def gen_memory_growth(trades: list[dict], rng: random.Random) -> list[dict]:
    out, total = [], 0
    for monday, chunk in _weeks(trades):
        total += len(chunk) + rng.randrange(0, 4)
        up = sum(1 for t in chunk if t["pnl_r"] > 0)
        down = sum(1 for t in chunk if t["pnl_r"] <= -1)
        rest = len(chunk) - up - down
        ranging = rest // 2
        volatile = rest - ranging
        out.append({
            "date": monday,
            "total_memories": total,
            "trending_up": up,
            "trending_down": down,
            "ranging": ranging,
            "volatile": volatile,
            "unknown": rng.randrange(0, 3),
        })
    return out


def gen_owm(trades: list[dict], rng: random.Random) -> list[dict]:
    """Recall-quality scores drift up as the memory store fills."""
    out = []
    weeks = _weeks(trades)
    for i, (monday, chunk) in enumerate(weeks):
        prog = i / max(1, len(weeks) - 1)
        base = 0.38 + 0.22 * prog
        def s(off: float) -> float:
            return round(min(0.95, max(0.05, base + off + rng.gauss(0, 0.035))), 2)
        avg_q, avg_sim = s(0.06), s(-0.04)
        avg_rec, avg_conf, avg_aff = s(0.02), s(0.01), s(-0.03)
        out.append({
            "date": monday,
            "avg_total": round((avg_q + avg_sim + avg_rec + avg_conf + avg_aff) / 5, 2),
            "avg_q": avg_q, "avg_sim": avg_sim, "avg_rec": avg_rec,
            "avg_conf": avg_conf, "avg_aff": avg_aff,
            "query_count": len(chunk) * 3 + rng.randrange(0, 8),
        })
    return out


def gen_calibration(trades: list[dict], rng: random.Random) -> list[dict]:
    """Sample across the confidence range so the chart shows a real slope."""
    buckets: dict[int, list[dict]] = {}
    for t in trades:
        buckets.setdefault(int(t["confidence"] * 10), []).append(t)
    out = []
    for b in sorted(buckets):
        for t in rng.sample(buckets[b], min(4, len(buckets[b]))):
            out.append({
                "trade_id": t["id"],
                "entry_confidence": t["confidence"],
                "actual_pnl_r": t["pnl_r"],
                "strategy": DISPLAY[t["strategy"]],
            })
    return out


def gen_strategy(name: str, trades: list[dict]) -> dict:
    spec = STRATEGY_SPEC[name]
    mine = [t for t in trades if t["strategy"] == name]
    rs = [t["pnl_r"] for t in mine]

    by_session: dict[str, list[float]] = {}
    for t in mine:
        by_session.setdefault(t["session"], []).append(t["pnl_r"])
    ranked = sorted(by_session.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))

    heat: dict[tuple[str, str], list[float]] = {}
    for t in mine:
        heat.setdefault((t["session"], t["day"]), []).append(t["pnl"])

    return {
        "_disclaimer": DISCLAIMER,
        "name": DISPLAY[name],
        "total_trades": len(mine),
        "win_rate": wr_of(rs),
        "profit_factor": pf_of(rs),
        "avg_pnl_r": round(sum(rs) / len(rs), 2),
        "avg_hold_seconds": int(sum(t["hold_seconds"] for t in mine) / len(mine)),
        # bug fix: these were the same string in the shipped strategy-im /
        # strategy-pb files. Ranked by mean R, so they cannot collide.
        "best_session": ranked[-1][0],
        "worst_session": ranked[0][0],
        "baseline_pf": spec["baseline_pf"],
        "baseline_wr": spec["baseline_wr"],
        "trades": [
            {
                "id": t["id"], "date": t["date"], "side": t["side"],
                "pnl": t["pnl"], "pnl_r": t["pnl_r"], "session": t["session"],
                "hold_seconds": t["hold_seconds"],
            }
            for t in mine[-20:]
        ],
        "session_heatmap": [
            {
                "session": s, "day": d, "trades": len(v),
                "avg_pnl": round(sum(v) / len(v), 2),
            }
            for (s, d), v in sorted(heat.items())
        ],
    }


def gen_reflections(trades: list[dict]) -> list[dict]:
    out = []
    for monday, chunk in _weeks(trades)[-20:]:
        rs = [t["pnl_r"] for t in chunk]
        pnl = sum(t["pnl"] for t in chunk)
        pf = pf_of(rs)
        grade = "A" if pf >= 1.8 else "B" if pf >= 1.2 else "C" if pf >= 0.9 else "D"
        worst = min(chunk, key=lambda t: t["pnl_r"])
        top = max(set(t["strategy"] for t in chunk),
                  key=lambda s: sum(t["pnl"] for t in chunk if t["strategy"] == s))
        out.append({
            "date": monday,
            "type": "weekly_review",
            "grade": grade,
            "strategy": DISPLAY[top],
            "summary": (
                f"Week of {monday}: {len(chunk)} trades, PnL ${pnl:+,.0f}, "
                f"PF {pf}, WR {wr_of(rs):.0%}. Worst trade {worst['pnl_r']}R "
                f"in {worst['session']}."
            ),
            "full_path": f"weekly_reviews/{monday}_weekly.md",
        })
    return out


def gen_adjustments(trades: list[dict], strategies: dict[str, dict]) -> list[dict]:
    """Parameter changes that follow from what the session data actually says."""
    def avg_r(name: str, session: str) -> tuple[float, int]:
        rs = [t["pnl_r"] for t in trades
              if t["strategy"] == name and t["session"] == session]
        return (sum(rs) / len(rs) if rs else 0.0), len(rs)

    def fmt(v: float) -> str:
        # keep -0.00R off the screen; it is not a reason for anything
        return f"{v:+.2f}".replace("-0.00", "0.00")

    out, i = [], 0
    for name, s in strategies.items():
        i += 1
        ts = trades[-1]["ts"] - timedelta(days=30 - i * 7)
        w_avg, w_n = avg_r(name, s["worst_session"])
        b_avg, b_n = avg_r(name, s["best_session"])

        # Only emit an adjustment the evidence actually supports. Cutting size
        # on a session averaging -0.00R is noise dressed as a decision.
        if w_avg < -0.05:
            out.append({
                "id": f"ADJ-{i:03d}",
                "timestamp": ts.isoformat(),
                "adjustment_type": "session_reduce",
                "parameter": f"{DISPLAY[name]}.{s['worst_session'].lower()}.max_lot",
                "old_value": "1.0", "new_value": "0.5",
                "reason": (f"{DISPLAY[name]} {s['worst_session']} session avg "
                           f"{fmt(w_avg)}R over {w_n} trades"),
                "status": "applied",
                "strategy": DISPLAY[name],
            })
        if b_avg > 0.10:
            out.append({
                "id": f"ADJ-{i:03d}B",
                "timestamp": (ts + timedelta(days=2)).isoformat(),
                "adjustment_type": "session_increase",
                "parameter": f"{DISPLAY[name]}.{s['best_session'].lower()}.max_lot",
                "old_value": "1.0", "new_value": "1.3",
                "reason": (f"{DISPLAY[name]} {s['best_session']} session avg "
                           f"{fmt(b_avg)}R over {b_n} trades"),
                "status": "applied",
                "strategy": DISPLAY[name],
            })

        # A losing strategy is the one the memory layer exists to catch.
        if s["profit_factor"] < 1.0:
            out.append({
                "id": f"ADJ-{i:03d}C",
                "timestamp": (ts + timedelta(days=4)).isoformat(),
                "adjustment_type": "strategy_suspend",
                "parameter": f"{DISPLAY[name]}.enabled",
                "old_value": "true", "new_value": "false",
                "reason": (f"{DISPLAY[name]} PF {s['profit_factor']} below 1.0 "
                           f"over {s['total_trades']} trades "
                           f"(baseline {s['baseline_pf']})"),
                "status": "proposed",
                "strategy": DISPLAY[name],
            })

    out.sort(key=lambda a: a["timestamp"])
    return out


def gen_beliefs(trades: list[dict]) -> list[dict]:
    """Beta-distributed beliefs whose alpha/beta are the real win/loss counts."""
    out = []
    combos: dict[tuple[str, str], list[float]] = {}
    for t in trades:
        combos.setdefault((t["strategy"], t["session"]), []).append(t["pnl_r"])

    for i, ((name, session), rs) in enumerate(
            sorted(combos.items(), key=lambda kv: -len(kv[1])), start=1):
        # The proposition claims profitability, so alpha/beta must count
        # profitable vs unprofitable stretches - not individual wins. Counting
        # wins made a +0.30R combo display "confidence 0.514", and a profitable
        # NY combo display 0.427, which contradicts the sentence beside it.
        blocks = [rs[j:j + 10] for j in range(0, len(rs) - 9, 10)]
        alpha = sum(1 for b in blocks if sum(b) > 0) + 1
        beta = sum(1 for b in blocks if sum(b) <= 0) + 1
        conf = alpha / (alpha + beta)
        avg = sum(rs) / len(rs)
        trend = "strong" if avg > 0.25 else "weak" if avg < -0.05 else "neutral"
        out.append({
            "id": f"BEL-{i:03d}",
            "proposition": (
                f"{DISPLAY[name]} is profitable in the {session} session "
                f"(avg {avg:+.2f}R)"
            ),
            "alpha": alpha, "beta": beta,
            "confidence": round(conf, 3),
            "strategy": DISPLAY[name],
            "regime": None,
            "sample_size": len(rs),
            "trend": trend,
        })
    return out


def gen_dreams(trades: list[dict], rng: random.Random) -> list[dict]:
    """Counterfactual replays: same tape, with and without recall."""
    out, base_ts = [], trades[-1]["ts"]
    configs = [
        ("no_memory", None, False, 1.00),
        ("episodic_only", "episodic", False, 1.09),
        ("full_recall", "episodic+semantic+affective", True, 1.21),
    ]
    for i, (cond, mem, reso, mult) in enumerate(configs, start=1):
        n = 120
        pf = round(1.04 * mult, 2)
        wr = round(min(0.62, 0.42 * (1 + (mult - 1) * 0.5)), 2)
        out.append({
            "_disclaimer": DISCLAIMER,
            "id": f"dream-{i:03d}",
            "timestamp": (base_ts - timedelta(hours=6 * i)).isoformat(),
            "condition": cond,
            "trades": n,
            "pf": pf,
            "pnl": round((pf - 1) * n * 0.55 * R_DOLLARS, 2),
            "wr": wr,
            "has_memory": mem is not None,
            "memory_type": mem,
            "resonance_detected": reso,
        })
    return out


def gen_evolution(rng: random.Random) -> dict:
    def fitness(sharpe, wr, pf, pnl_r, dd, n):
        return {
            "sharpe_ratio": sharpe, "win_rate": wr, "profit_factor": pf,
            "total_pnl": round(pnl_r * R_DOLLARS, 2),
            "max_drawdown_pct": dd, "trade_count": n,
        }

    graduated = [
        ("HYP-001A", "London Open Breakout", 0,
         fitness(0.84, 0.47, 1.31, 38.2, 0.082, 146),
         fitness(0.61, 0.45, 1.19, 12.4, 0.094, 58)),
        ("HYP-004C", "NY Reversal After Asia Range", 1,
         fitness(0.77, 0.44, 1.26, 29.6, 0.071, 121),
         fitness(0.48, 0.43, 1.12, 7.1, 0.088, 47)),
        ("HYP-007B", "Pre-News Volatility Fade", 1,
         fitness(0.69, 0.51, 1.22, 21.3, 0.066, 94),
         fitness(0.39, 0.48, 1.08, 3.8, 0.079, 36)),
        ("HYP-011D", "Session Handover Momentum", 2,
         fitness(0.72, 0.46, 1.24, 25.0, 0.075, 108), None),
    ]
    graveyard = [
        ("HYP-X01", "Hourly RSI Crossover", 0, "Negative Sharpe in IS (-0.31)",
         fitness(-0.31, 0.38, 0.87, -14.2, 0.163, 132)),
        ("HYP-X02", "Round Number Bounce", 0, "PF below 1.05 gate (0.98)",
         fitness(0.04, 0.41, 0.98, -2.1, 0.118, 97)),
        ("HYP-X03", "Weekend Gap Fill", 0, "Sample too small (n=19)",
         fitness(0.22, 0.53, 1.14, 2.6, 0.061, 19)),
        ("HYP-X04", "MA Ribbon Stack", 1, "OOS Sharpe collapsed (0.81 -> -0.12)",
         fitness(0.81, 0.49, 1.29, 26.4, 0.079, 115)),
        ("HYP-X05", "Volume Spike Chase", 1, "Max drawdown 21.4% over gate",
         fitness(0.58, 0.44, 1.17, 18.9, 0.214, 103)),
        ("HYP-X06", "Fractal Divergence", 2, "Negative expectancy OOS (-0.09R)",
         fitness(0.44, 0.42, 1.11, 9.8, 0.092, 76)),
    ]
    started = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)
    return {
        "run_id": "EVO-7F3A21",
        "symbol": "XAUUSD",
        "timeframe": "1h",
        "generations": 3,
        "per_generation": [
            {"generation": 0, "hypotheses_count": 10, "graduated_count": 1, "eliminated_count": 3},
            {"generation": 1, "hypotheses_count": 10, "graduated_count": 2, "eliminated_count": 2},
            {"generation": 2, "hypotheses_count": 10, "graduated_count": 1, "eliminated_count": 1},
        ],
        "graduated": [
            {"hypothesis_id": h, "pattern_name": p, "generation": g,
             "fitness_is": fi, "fitness_oos": fo}
            for h, p, g, fi, fo in graduated
        ],
        "graveyard": [
            {"hypothesis_id": h, "pattern_name": p, "generation": g,
             "elimination_reason": r, "fitness_is": fi}
            for h, p, g, r, fi in graveyard
        ],
        "total_graduated": len(graduated),
        "total_graveyard": len(graveyard),
        "total_tokens": 45000,
        "total_backtests": 30,
        "started_at": started.isoformat(),
        "completed_at": (started + timedelta(minutes=15, seconds=30)).isoformat(),
    }


# ── orchestration ──────────────────────────────────────────────────────
def write(name: str, payload) -> None:
    path = MOCK_DIR / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print(f"  wrote {name:24s} {path.stat().st_size:>7,} bytes")


def build(seed: int) -> dict:
    rng = random.Random(seed)
    trades = simulate(rng)
    equity, mdd = gen_equity(trades)
    overview = gen_overview(trades, mdd)

    strategies = {n: gen_strategy(n, trades) for n in STRATEGY_SPEC}

    print(f"\nseed {seed}: {overview['total_trades']} trades  "
          f"PnL ${overview['total_pnl']:+,.0f} "
          f"({overview['total_pnl'] / ACCOUNT:+.1%})  "
          f"PF {overview['profit_factor']}  "
          f"WR {overview['win_rate']:.1%}  "
          f"MDD {overview['max_drawdown_pct']:.2%}")

    write("overview.json", overview)
    write("equity-curve.json", equity)
    write("rolling-metrics.json", gen_rolling(trades))
    write("memory-growth.json", gen_memory_growth(trades, rng))
    write("owm-score-trend.json", gen_owm(trades, rng))
    write("confidence-cal.json", gen_calibration(trades, rng))
    for name, payload in strategies.items():
        write(f"strategy-{STRATEGY_SPEC[name]['slug']}.json", payload)
    write("reflections.json", gen_reflections(trades))
    write("adjustments.json", gen_adjustments(trades, strategies))
    write("beliefs.json", gen_beliefs(trades))
    write("dream-results.json", gen_dreams(trades, rng))
    write("evolution.json", gen_evolution(rng))
    return overview


def check() -> None:
    """Re-read from disk and assert the things the old set got wrong."""
    load = lambda n: json.loads((MOCK_DIR / n).read_text(encoding="utf-8"))
    ov, eq = load("overview.json"), load("equity-curve.json")
    strats = [load(f"strategy-{s['slug']}.json") for s in STRATEGY_SPEC.values()]

    fails = []

    if eq[-1]["trade_count"] != ov["total_trades"]:
        fails.append(f"equity trade_count {eq[-1]['trade_count']} != "
                     f"overview total_trades {ov['total_trades']}")

    s_sum = sum(s["total_trades"] for s in strats)
    if s_sum != ov["total_trades"]:
        fails.append(f"strategy trades sum {s_sum} != overview {ov['total_trades']}")

    series_mdd = max(p["drawdown_pct"] for p in eq)
    if abs(series_mdd - ov["max_drawdown_pct"]) > 0.0002:
        fails.append(f"equity series MDD {series_mdd} != overview "
                     f"{ov['max_drawdown_pct']}")

    if abs(round(eq[-1]["cumulative_pnl"], 2) - ov["total_pnl"]) > 0.02:
        fails.append(f"equity final PnL {eq[-1]['cumulative_pnl']} != overview "
                     f"{ov['total_pnl']}")

    if abs(ACCOUNT + ov["total_pnl"] - ov["current_equity"]) > 0.02:
        fails.append("current_equity != account + total_pnl")

    under = [p for p in eq if ACCOUNT + p["cumulative_pnl"] <= 0]
    if under:
        fails.append(f"{len(under)} points have equity <= 0")

    for s in strats:
        if s["best_session"] == s["worst_session"]:
            fails.append(f"{s['name']}: best_session == worst_session "
                         f"({s['best_session']})")

    # scale-invariant sanity: expectancy per trade in R
    exp_r = ov["total_pnl"] / R_DOLLARS / ov["total_trades"]
    if not 0.0 < exp_r < 0.30:
        fails.append(f"expectancy {exp_r:.3f}R/trade outside plausible band")

    wr_num = sum(s["total_trades"] * s["win_rate"] for s in strats) / s_sum
    if abs(wr_num - ov["win_rate"]) > 0.01:
        fails.append(f"weighted strategy WR {wr_num:.3f} != overview "
                     f"{ov['win_rate']}")

    for n in ("overview.json", "dream-results.json",
              *[f"strategy-{s['slug']}.json" for s in STRATEGY_SPEC.values()]):
        raw = (MOCK_DIR / n).read_text(encoding="utf-8")
        if "Illustrative demo dataset" not in raw:
            fails.append(f"{n} missing disclaimer")

    print("\n--- consistency check ---")
    print(f"  expectancy      {exp_r:+.3f} R/trade")
    print(f"  total return    {ov['total_pnl'] / ACCOUNT:+.2%}")
    print(f"  max drawdown    {ov['max_drawdown_pct']:.2%}")
    print(f"  profit factor   {ov['profit_factor']}")
    print(f"  win rate        {ov['win_rate']:.1%}")
    print(f"  min equity      ${ACCOUNT + min(p['cumulative_pnl'] for p in eq):,.0f}")
    if fails:
        print("\nFAIL:")
        for f in fails:
            print("  x", f)
        raise SystemExit(1)
    print("\n  PASS - all cross-file invariants hold")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    # Seed chosen by sweeping 20260000-20261199 for a sample path where the
    # aggregate lands in band AND one of the three strategies is a loser
    # (13 of 1,200 qualified). A board where everything wins is the less
    # believable one, and the Adjustments / Beliefs views have nothing to show
    # if there is no losing strategy to cut. Locked for reproducibility.
    ap.add_argument("--seed", type=int, default=20260687)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    build(args.seed)
    if args.check:
        check()
