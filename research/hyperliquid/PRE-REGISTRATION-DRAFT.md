# Pre-Registration — DRAFT for Sean's approval

> Status: **Part 1 APPROVED & LOCKED 2026-05-30** — this commit is the timestamped pre-registration record the paper cites (spec §7.1/§7.2). **Part 2 (detector) locks after Plan 2's synthetic Monte-Carlo calibration, before the locked test is read.** Values chosen on principle + the 2026-05-30 viability scoping (`COHORT-REPORT.md`) — **NOT fit to the locked test set, which stays untouched until the detector is frozen.**
> Spec: `docs/superpowers/specs/2026-05-30-copytrading-drift-paper-design.md` · Headline cohort LOCKED: idiosyncratic lead-time (A) + crash-day discrimination (B).

Two parts: **Part 1 = data/cohort params lockable NOW**; **Part 2 = detector params lockable AFTER Plan 2's synthetic Monte-Carlo calibration** (the detector must be calibrated on synthetic data, not real outcomes, then frozen before the real locked test).

---

## Part 1 — Data & cohort (lock NOW)

| # | Parameter | Recommended value | Rationale |
|---|---|---|---|
| 1 | **Universe** | Hyperliquid leaderboard snapshot (37,872 addrs), filtered to: first fill ≤ T₀, **pre-T₀ peak perp account value ≥ \$25k**, ≥ 2 pre-T₀ equity points | "Master worth copying" floor; removes dust; ensures a pre-T₀ baseline exists. Outcome-blind (no survival filter). |
| 2 | **T₀ (freeze date)** | **2025-06-01 UTC** | Spans multiple 2025–26 volatility regimes → more *independent* crash events (the real power unit); far enough back that leaderboard accounts plausibly predate it. **Coverage verified in the run** — if too few qualify, fall back to 2025-09-01. |
| 3 | **Window end** | **2026-04-30 UTC** (≈11-month forward window) | Leaves a clean held-out gap before "now"; ~2× the viability window → expect ~2× independent events. |
| 4 | **Blow-up drawdown `dd_pct`** | **0.70** primary; robustness reruns at **0.50** and **0.85** | 70% peak-to-trough = catastrophic/account-dead. Report all three so the threshold isn't a lucky pick. |
| 5 | **`recovery_frac` / `recovery_horizon`** | **0.80 / 30 days** | Matches the coarse (~weekly) `portfolio` equity granularity; recovery to 80% of peak within a month cancels a transient dip. |
| 6 | **Withdrawal filter** | blow-up counts only if **cumulative-PnL drop ≥ 0.5 × equity drop** across the crater | Excludes equity drops that are withdrawals, not losses. Viability median ratio 0.92 → most craters already qualify. |
| 7 | **Market-event-day threshold `τ`** | a UTC day is **market-event** if **≥ 3% of the active universe** craters that day; else **idiosyncratic** | Behaviorally-independent blow-ups cannot plausibly synchronize >3% of masters on one day without a common shock. Cleanly separates 2026-01-07 (59% in viability) from the idiosyncratic tail (<3%). |
| 8 | **Min-baseline inclusion** | **≥ 50 fills AND ≥ 14 days** of history before T₀ (within the available ≤10k-fill window) | Enough to estimate the 3 behavioral axes. Addresses whose 10k-fill window doesn't reach T₀ are **flagged truncated + excluded from behavioral analysis**, reported as a named selection-bias line (biases toward lower-frequency masters — disclosed). |
| 9 | **Cohorts** | **Idiosyncratic** (non-event-day, loss-confirmed, baseline-met) = Claim A. **Crash-day** (event-day blow-ups vs matched survivors) = Claim B. **Stable** (no blow-up in window, baseline-met). **Volatility-null** = event days, to test the detector doesn't fire on stable masters just because the market crashed. | Direct from the locked headline decision + viability finding. |
| 10 | **Processing** | Stage 1: equity-only labeling on the **full qualifying universe** (1 call/addr, throttled ≥0.4s + retry on 429). Stage 2: full trajectory (fills/orders/ledger) only for the labeled cohort (all blow-ups + a seed-fixed matched stable sample). | No sampling bias on labeling; bounded cost on the expensive pulls. |

## Part 2 — Detector & gates (lock AFTER Plan 2 synthetic MC, before real test)

> **Status 2026-05-31 — detector machinery BUILT + validated; final lock DEFERRED to Plan 3 (Sean approved).**
> Plan 2 is complete: `research/hyperliquid/detector/` holds the full pipeline (per-trade behavioral
> primitives → bucket-close per-axis observations → per-axis mSPRT reusing `ssrt/core.py` →
> Holm-min-gate + sustained-M composite → 70% guard band), the label-blind 2-state HMM synthetic
> generator, the calibration grid + pickup rule, and the discipline-only ablation harness — **154
> tests green**, every phase implementer→spec-review→code-review. A synthetic-anchor demo calibration
> validates the machinery end-to-end (`research/hyperliquid/detector/calibration_result_demo.json`:
> demo winner 4h/M=2/equal/κ=14, Type-I 0.0 / power 1.0 — power saturates because synthetic anchors
> are noise-free; **NOT a pre-registered number**).
> **Decision (Sean, 2026-05-31): the FINAL Part-2 lock happens at the START of Plan 3**, after the
> real tuning-split marginals (40% split, outcome-blind, no locked-test contact) are computed — so
> the frozen grid-winner tuple reflects real master behavior, not synthetic placeholders. The
> detector form + α (#11–12) and the composite target / guard band / ablation bar (#13–15) below are
> fixed now; only the winning (bucket/M/τ/weights/κ) tuple awaits the real tuning-split calibration run.
>
> **Plan 3 pre-lock checklist (from Plan-2 final whole-implementation review — firewall verdict PASS):**
> (a) **SNR scaling** — generator scatter is 1.4826·MAD while AxisSPRT uses σ=1 and baseline std=MAD,
>     so z-scores have std≈1.4826 and the effective per-primitive SNR is δ/1.4826, not δ. Internally
>     self-consistent (calibration uses the same scale on both sides), but before locking either ALIGN
>     (baseline std=1.4826·MAD, or AxisSPRT σ=1.4826, or drop the 1.4826 so δ=SNR) OR document the δ→SNR
>     map in the methods section — else the paper's SNR table is off by 1.4826×.
> (b) **κ identifiability** — synthetic calibration sets self_stats==universe_stats, so shrinkage returns
>     the median regardless of κ → κ is an INERT knob and the demo winner's κ carries no signal. Plan 3
>     MUST build the baseline from real pre-T₀ (self) vs tuning-split (universe) as DISTINCT stats so κ
>     becomes live and its locked value is meaningful.
> (c) **integration test** — add an end-to-end run_detector test with self_stats≠universe_stats to catch
>     real-baseline wiring errors before deployment.
>
> **Real-data findings (2026-05-31 scaled run — see `MORNING-BRIEF-2026-05-31.md`):**
> (d) **Sparse-primitive normalization** — count/rate primitives (topup_count, loser_add_count, …) are 0
>     in most real buckets → MAD=0 → z-scores explode → type_i≈1. Patched with std-based scale in the
>     scaled run; Plan 3 must decide the proper transform (log1p / rate / z-clip) before locking.
> (e) **Behavioral baseline availability** — the 10k-fill cap × T0=2025-06-01 means high-freq masters
>     have NO pre-T0 fill baseline (`meets_baseline` failed for all 140 fetched). DECISION NEEDED (affects
>     pre-reg): later T₀ / early-window baseline / equity-derived proxies / accept low-freq-biased cohort.
> (f) **Nested order structure** — real `historicalOrders` nest under "order"; `order_events` fixed to
>     handle both (mock flat + real nested). 154 tests green.
> Indicative real-data smoke: frozen detector fired on 3/6 idiosyncratic blow-up masters, carrying axis
> = exposure, median lead ≈ 492h (~20d) — NOT a pre-reg number (in-window self-baseline, no B1/B2/B3).

| # | Parameter | Recommended | Rationale |
|---|---|---|---|
| 11 | **Primary detector** | per-axis one-sided sequential test (mSPRT-style), sign per axis (exposure↑, discipline↓, tilt↑); composite = Holm-corrected across 3 axes, sustained ≥ **M** windows | One committed detector; binary-CUSUM remnants stripped from the paper code path. |
| 12 | **Per-axis α** | **0.01** | mSPRT validated Type-I ≈ 0.008 (22,500 MC). |
| 13 | **Composite M + threshold** | set on **synthetic MC** to hit **composite Type-I ≤ 0.05, power ≥ 0.70**; frozen before real test | The single-stream Type-I does NOT transfer to the 3-axis composite — fresh MC mandatory. |
| 14 | **Guard band** | alert counts as "early" only while equity ≥ **70% of peak** AND before the first liquidation fill | Anti-label-leakage (Exposure/Tilt are equity-coupled). |
| 15 | **Ablation pass bar** | discipline-only detector retains **≥ 50%** of full-detector lead-time, event-clustered CI excludes 0 | Proves the signal isn't just an equity shadow. |

## Part 3 — Claim gates (falsifiable, pre-set)

| Claim | Primary gate (pre-registered) |
|---|---|
| **A — lead-time (HEADLINE)** | On the idiosyncratic locked-test cohort: median lead-time advantage over **best of {B1 leverage-percentile, B2 drawdown-velocity, B3 leverage-up-and-add}** is **> 0**, event-clustered 95% CI **excludes 0**. (Report the hours; no minimum pre-set beyond >0.) |
| **B — discrimination** | Idiosyncratic prediction **AUC 95%-CI lower bound > 0.65**; **volatility-null FPR < 0.10**; **PPV ≥ 0.30** at the operating threshold (honest given low base rate) + cost curve. |
| **C — follower impact** | dimensionless sensitivity surface only; **no single \$ figure in the abstract**; no statistical gate. |

## Part 4 — Statistical procedure (lock NOW)

- **Event-clustered bootstrap** clustering by **UTC liquidation-day** (not by trader), **5,000** resamples; report **effective-N = number of independent crash clusters**; **leave-one-event-out** robustness.
- **3-way split**, seed-fixed by address with event-clustering respected: **tuning 40% / validation 20% / LOCKED test 40%**. Detector + α + M + all targets frozen in this commit's successor (post-MC) **before** the locked test is read; publish the commit hash in the paper.
- **Robustness reruns**: dd_pct ∈ {0.5, 0.7, 0.85}; T₀ fallback {2025-06, 2025-09}.

## Part 5 — NOT pre-registered (exploratory, labelled as such)
Behavioral-axis feature engineering details; the follower-impact model; any post-hoc subgroup analysis; case studies (James Wynn et al. — appendix, excluded from all stats).

---

## Sean's call — ✅ APPROVED 2026-05-30 (all five as recommended)
1. **T₀ = 2025-06-01 / window end 2026-04-30** ✅
2. **dd_pct 0.70** primary (+0.5/0.85 robustness) ✅
3. **Market-event τ = 3% of active universe** ✅
4. **Universe floor: pre-T₀ peak ≥ \$25k** ✅
5. **Claim gates** (A lead-time>0 CI-excludes-0; B AUC-CI>0.65 / FPR<0.10 / PPV≥0.30; C no \$ in abstract) ✅

This commit IS the timestamped Part-1 pre-registration → Plan 2 (detector) begins against these frozen rules; Part 2 locks after the synthetic MC, before the locked test.

> **Context note:** Plan 2 (the detector + synthetic MC) is a fresh multi-day chunk. Recommend starting it in a **new session** for context hygiene — this repo's CLAUDE.md + spec + COHORT-REPORT + this draft fully capture the resume point, so zero context is lost.
