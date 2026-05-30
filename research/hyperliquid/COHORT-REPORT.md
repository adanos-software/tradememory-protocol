# Cohort Viability Report — Task 9 (Plan 1)

> Status: **VIABILITY / SCOPING pass — provisional params, NOT the pre-registered run.**
> Date: 2026-05-30 · Spec §6/§7 · Plan `docs/superpowers/plans/2026-05-30-hyperliquid-data-pipeline.md`
> Purpose: decide go/no-go on whether a frozen-at-T₀ Hyperliquid universe yields enough real,
> behaviorally-driven blow-ups (and enough *independent* events) to power the paper.

## Method (provisional)
- **Universe**: Hyperliquid leaderboard = **37,872 addresses** (`stats-data.hyperliquid.xyz/Mainnet/leaderboard`).
- **Sample**: 300 addresses, every 126th rank (spread across ranks, not just top survivors).
- **Equity source**: `portfolio` perpAllTime `accountValueHistory` (goes back months–2yr even when fills hit the 10k cap).
- **Labeler**: the repo's forward-only `forward_only_blowup_time` (dogfooded), seeded with pre-T₀ peak.
- **Provisional params** (NOT pre-registered): T₀ = 2026-01-01, window end 2026-05-30, dd > 70%, recovery_frac 0.80, recovery_horizon 30d.
- **Withdrawal-vs-loss confound**: checked via `pnlHistory` — ratio = cumulative-PnL-drop ÷ equity-drop across the crater.

## Results
| Metric | Value |
|---|---|
| Sampled / included / excluded (short pre-T₀ history) / errors (429 rate-limit) | 300 / **245** / 46 / 9 |
| Blow-ups (equity crater > 70%, no recovery) | **218** |
| Stable | 27 |
| Raw base rate | **89%** |
| **effective_n_events (independent UTC crash-days)** | **24** |
| Loss-confirmed (PnL drop ≥ 50% of equity drop) | **159 / 218** |
| Median PnL/equity-drop ratio | **0.92** (most craters are genuine trading losses, not withdrawals) |

## ⚠️ Critical finding: blow-ups cluster on market-crash days
The raw 89% base rate is **market-crash-inflated**. Crash-day histogram:

`2026-01-07: 144` · `2026-01-14: 21` · Feb-04: 7 · Feb-11: 5 · Jan-28: 4 · Mar-11: 4 · Apr-08: 3 · Mar-04: 3 · …

**144 of 218 blow-ups (66%) happened on a single day (2026-01-07)** — a market-wide dump, not idiosyncratic behavioral blow-ups. This is exactly the time-clustering the spec's event-clustered stats (§7.3) and volatility-null control (§6) were designed for, and it sharpens the cohort design:

- **Idiosyncratic blow-ups** (a master drifts and dies on a NON-crash day) ≈ **218 − (144+21) = ~53 across ~22 independent days**. Loss-confirmed subset ≈ **~38**. These are where *behavioral-drift early warning has unique value* (the trigger is the master's own behavior, not an exogenous shock).
- **Market-event blow-ups** (crash days): not "predict the blow-up" but a **discrimination** task — given the same shock, who was over-leveraged/tilted going in and died vs who survived. Still valuable (Claim B), different framing.

## Go/No-Go: **GO** (with a sharpened cohort design)
Real, abundant, mostly-genuine-loss blow-ups exist and are detectable from free public data; equity history reaches across a useful T₀. The paper is viable. But the pre-registered run must:

1. **Tag each blow-up as idiosyncratic vs market-event** via cross-sectional blow-up density on its UTC day (a market-event day = many masters crater simultaneously). Report both cohorts separately.
2. **Extend the window** beyond Jan–May 2026 (e.g. T₀ in 2024 → 2026) to accumulate more *independent* crash events and more idiosyncratic blow-ups — effective-N (24 here, dominated by a few days) is the real power unit, not the raw 218.
3. **Filter withdrawals** (require PnL-drop ≈ equity-drop) so the cohort is genuine losses.
4. **Make the volatility-null control central** (the detector must NOT just fire on market crashes).
5. **Throttle + retry** the fetcher (429s appeared at ~0.12s spacing) and respect the 10k-fills cap for behavioral baselines.

## Next (needs Sean before the pre-registered run)
- Confirm **T₀ + window** (recommend widening, e.g. T₀ = 2024-06, window → 2026-05).
- Confirm **dd_pct / horizon** and the **market-event-day threshold** (these become pre-registered values, frozen in a timestamped commit before the locked test).
- Decide **headline cohort**: idiosyncratic-blow-up lead-time (purest behavioral story) vs crash-day discrimination vs both.
