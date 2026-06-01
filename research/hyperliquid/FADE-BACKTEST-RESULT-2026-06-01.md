# FADE backtest result (2026-06-01) — exploratory, in-sample

> Q: does fading hot/parabolic masters make money? Signal = fade a master after a
> strong recent trailing run-up (pnl-based, causal). Universe = 4,121 masters with
> refetched pnlHistory (2,621 idiosyncratic blowups + 1,500 seed-fixed stable),
> reweighted to the Stage-1 qualified population (stable ×2.67). Inverse-copy return
> on TRADING PnL (not equity). Event-clustered. Costs: funding 20%/yr×H/365 + 0.1% fee.

## Verdict: real but discipline-dependent tail strategy — NOT a money-printer
- **Net-of-cost reweighted mean is POSITIVE** in almost all grid cells; best
  **W=14, R_hot=100%, H=30d → netMean +0.238/event** (win 49%, clustered t=1.93, n=2077, 139 clusters).
- **BUT uncapped (no stop) is NEGATIVE** (wMean −0.02 to −0.20): shorting a master who
  moons loses >100% (p5 = −0.76 to −2.17). → profitable ONLY with a hard stop (cap loss ≈ −1).
- **Win rate <50% (41–49%), median ≈0** → classic fat-tail short: bleed small most of
  the time, win big on the crashes.
- **Statistically noisy**: event-clustered t mostly 1–2 (best 2.17 at W=30/R=100%/H=30).
  Real-ish edge, in-sample positive, but NOT bulletproof — needs OOS.
- **Conservative**: market-event (crash-day) blow-ups EXCLUDED → real fade likely better in crashes.
- **Pattern**: fade the MOST extreme run-ups (R=100%) and hold LONGER (H=30) = best (euphoria reversion).

## Best cells (net-of-cost, reweighted)
| W | R_hot | H | n_ev | win% | netMean | clustered t |
|---|---|---|---|---|---|---|
| 14 | 100% | 30 | 2077 | 49% | **+0.238** | 1.93 |
| 30 | 100% | 30 | 2319 | 48% | +0.157 | **2.17** |
| 14 | 50% | 30 | 2884 | 47% | +0.136 | 1.85 |
| 14 | 30% | 30 | 3241 | 47% | +0.165 | 1.83 |

## Interpretation (Sean's poker edge)
A −EV-looking, high-variance, fat-tail bet that is +EV ONLY under strict risk
management (bankroll/stop). Reckless degens blow up on the squeezes; a disciplined
player harvests the tail. Moat = discipline + the on-chain signal.

## Product implication
FADE vault is viable as **risk-managed tail-harvesting** (hard stops), NOT "easy money."
Dopamine/distribution via a public Degen Drift Index (publicly fading the hottest
masters, 麻吉大哥 archetype); profitability via discipline. Selling "passive yield"
would blow up + invite lawsuits.

## Honest caveats / next steps before real money
1. EXPLORATORY + IN-SAMPLE (grid scanned over W/R/H) — risk of overfit; the t-stats
   are borderline. Need OUT-OF-SAMPLE (time/coin holdout) to trust it.
2. The capped-at-−1 net assumes you can always exit at −100% (a violent gap can exceed it).
3. "Return" base = equity at signal (simplification); no per-coin position data.
4. Variant to test: fade "chronic-reckless" masters (prior blow-up history), not just run-up.
5. Going live tiny with own capital (the 30-day plan) IS the real OOS test.

Code: fade_fetch_pnl.py (pnl refetch), fade_backtest.py. Data: fade_pnl.json (gitignored, 18.8MB).
