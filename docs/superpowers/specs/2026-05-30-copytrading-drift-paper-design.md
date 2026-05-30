# Design Spec — Copy-Trading Blow-Up Early Warning Paper

> Status: DRAFT for review · Date: 2026-05-30 · Author: Sean Peng (Syuan Wei Peng), Mnemox AI
> Supersedes the framing of `docs/research/arxiv-paper-behavioral-drift.md` (self-monitoring SPC paper).
> Strategic context: `COPYTRADING-PIVOT-RESUME.md` + memory `tradememory-crypto-drift-pivot-2026-05-28.md`.

---

## TL;DR（繁中，給 Sean 快掃）

把現有那篇「self-monitoring CUSUM」論文 **reframe** 成旗艦：**在真實 Hyperliquid 鏈上資料上，偵測被跟單的 master trader 在「爆倉拖垮 follower」之前的行為漂移**。

- **Headline claim (A)**：偵測器在強平前中位數 **K 筆交易 / H 小時**就標紅；equity-threshold baseline (MaxDDStop) lead-time ≈ 0。
- **Rigor (B)**：爆倉 vs 穩定 master 的鑑別力（AUC），且市場級波動期不誤報。
- **Impact (C)**：估計可保護的 follower AUM（清楚標註「估計」）。
- **資料**：Hyperliquid 官方 API（已 spike 驗證可行，2026-05-30）。Ground truth = fill 的 `liquidation` key + equity crater。
- **現有論文回收**：MaxDDStop 結果 → 動機核心；BOCPD/DQS DEAD + SPC → methods 信譽。一個實驗不浪費。
- **撼動世界的點**：真錢、真人、真爆、鏈上可驗證、可審計（SHA-256）、給機構可部署的動作（凍結跟單）。不是 synthetic grid strategy。

---

## 1. Working title

**Primary**: *Early Warning of Copy-Trading Blow-Ups: Behavioral Drift Detection for Master Traders on On-Chain Perpetual Futures*

Alternatives:
- *Catching the Blow-Up Before It Spreads: Behavioral Drift Detection for Copy-Trading Master Traders*
- *Before the Liquidation: Lead-Time Detection of Master-Trader Behavioral Drift on Hyperliquid*

Target venue: arXiv **q-fin.TR** (endorsement secured — Yijia Xiao, UCLA, 2026-05-20). Cross-list candidates: cs.LG, cs.CE (needs endorser in those categories; optional).

---

## 2. The problem (institutional lens — what makes a bank/exchange care)

Copy trading lets thousands of *followers* mirror a *master trader*'s positions in real time. When a master's behavior degrades — over-leverage, revenge-adding into losses, abandoning stops — and they blow up, **the followers blow up with them, simultaneously, with no time to react.** This is:

- **Documented & regulator-flagged**: IOSCO FR/06/2025 ("Online Imitative Trading Practices: Copy…"), UK FCA + CFTC 2025–2026 finfluencer/copy-trading warnings.
- **Unmeasured**: no vendor-neutral, transparent way for a broker to know *which master is about to blow up my followers*, early enough to act.
- **Partially solved, badly**: ZuluTrade's ZuluGuard auto-closes drifting signal providers — but it is **forex-only, single-venue, and a black box** (14 years, no transparency, no crypto).

The institutional reader (Bybit / Bitget / OKX / OTSO / BTSE risk lead, or a regulator) cares about five things, and a paper is "world-shaking" to them only if it hits all five:

1. Names a risk they fear but **can't currently measure** → copy-trading blow-up contagion.
2. Proves it on **real, adversarial data** → on-chain perpetual blow-ups, real money, verifiable.
3. **Quantifies the money** → follower AUM at risk, lead-time in tradeable units.
4. Gives a **deployable control action** → throttle/freeze copy inflows + auditable evidence trail.
5. Is **transparent & auditable** → reproducible, SHA-256 audit chain (the anti-ZuluGuard).

## 3. The reframe (why this beats the current paper)

The current paper (`arxiv-paper-behavioral-drift.md`) asks: *can an agent monitor its own win rate to reduce its own drawdown?* Its headline finding is that a trivial equity-drawdown threshold (**MaxDDStop**) beats the behavioral CUSUM detector in 93.5% of strategies. As a standalone, that result tells an institution "behavioral monitoring isn't worth it" — the opposite of world-shaking.

**The copy-trading reframe inverts the MaxDDStop result into the paper's core motivation:**

> MaxDDStop wins **when you can observe your own equity in real time.** A copy-trading follower **cannot observe the master's equity drawdown in time** — by the time the master's equity has fallen far enough for an equity threshold to fire, the follower has *already* taken the loss. The only way to gain *lead-time* is to detect **behavioral** drift in the master's observable order-flow **before** it shows up as an equity crater.

So the prior paper's "failure" becomes the load-bearing argument: outcome-monitoring is necessary-but-too-late for the follower; behavioral monitoring is the only thing that can be early. Nothing from the prior work is wasted (see §9).

## 4. Core claims & metrics (pre-registered)

**Discipline: thresholds and cohort rules are fixed in this spec BEFORE touching test data.** This is the antidote to the prior paper's inflated `p < 10⁻⁶` (which came from non-independent strategies). We pre-register to make the result credible.

### Claim A — Lead-time (HEADLINE)
On a held-out set of real blow-up masters, the detector raises its first sustained alert a median of **K trades / H hours before** the blow-up event, with K and H reported with bootstrap CIs. Contrast against an equity-threshold baseline (the MaxDDStop analogue applied to the *master's* equity) whose lead-time is ≈ 0 by construction (it fires at the crater, not before).
- **Falsifiable failure**: if median lead-time ≤ equity-threshold lead-time, or CI includes 0, the headline claim fails.

### Claim B — Discrimination (RIGOR)
Across a population of masters over a fixed window, the detector separates *will-blow-up-within-Δ* from *will-not* with **AUC ≥ target**, AND the **false-positive rate during market-wide volatility windows** (null cohort, §6) stays below a pre-set bound — proving it detects *behavior*, not just *market moves*.
- **Falsifiable failure**: AUC ≤ 0.5 + margin, or volatility-null FPR exceeds bound.

### Claim C — Follower impact (IMPACT FRAME, clearly estimated)
Counterfactual: had a broker frozen copy inflows at first sustained alert, an estimated **$X of follower AUM / N copier-accounts** would have avoided the post-alert loss. Where real follower data is unavailable, estimate via on-chain copy-vault data (GMX/Perpy) or a clearly-labelled multiplier model; **every number tagged "estimated" with its assumption stated.**
- This is a *framing* contribution, not a statistical claim. No falsification gate; honesty gate instead (assumptions explicit, sensitivity range shown).

## 5. Method

### 5.1 Three orthogonal risk axes (not 8 factors)
Per codex+Opus review, collapse behavior into **3 orthogonal, volatility-normalized axes** with multiple-comparison correction across axes, and an explicit `insufficient_data` state when a window is too sparse:

| Axis | Captures | Example observables (all from verified API fields) |
|---|---|---|
| **Exposure** | leverage / size relative to account | position notional ÷ account value; size in ATR-normalized units; leverage creep |
| **Discipline** | risk-control hygiene | stop-loss/trigger order presence rate (`isTrigger`/`isPositionTpsl`), holding-time distribution, reduce-only behavior |
| **Tilt** | emotional/desperation drift | margin top-up frequency & acceleration (`deposit` ledger), adding into losing positions, trade-frequency spikes, win→loss streak response |

**Volatility normalization is mandatory** — size/equity or size/ATR — otherwise we can't distinguish "trader raised their bet" from "market got more volatile."

### 5.2 Detector
- **Continuous change-detection on each axis**, NOT binary CUSUM as the primary detector. Use the NIG (Normal-Inverse-Gamma) continuous changepoint from `changepoint.py`, and/or SSRT `mSPRT_t03` (the only method we validated with Type-I < 0.05; 81.4% power, Type-I=0.008 over 22,500 MC runs).
- **Composite alert** = sustained simultaneous drift across axes, multiple-comparison-corrected. "Sustained" defined (e.g., ≥ M consecutive windows) to control false alarms.
- Binary CUSUM, BOCPD, DQS, anti-resonance gate, CalibratedAgent are **excluded as primary** (all flagged DEAD/INVALID/wrong-tool in prior research — see §9; they appear only as honest negative-result context).

### 5.3 Ground truth (blow-up definition)
Two-tier, both verified retrievable in the 2026-05-30 spike:
1. **Formal liquidation** — fills carry a `liquidation` key (verified `True` on real data); gives liquidation timestamp at per-fill precision.
2. **Equity crater** — `portfolio` accountValueHistory peak → near-zero terminal collapse (verified: James Wynn $1.89M → $0). Captures capitulation/manual-death even without a formal liquidation tag.
- Blow-up event time T = earliest of (first liquidation fill in the terminal cascade) / (equity-crater inflection). Exact rule pre-registered before test data.

### 5.4 Auditability (the anti-ZuluGuard differentiator)
Each alert emits an auditable record: which axis drifted, the statistic value, the evidence window, the recommended action — hashed into the existing **SHA-256 linked audit chain** (`verify_audit_hash`, daily Merkle roots). This is what lets a broker defend a "freeze" decision to a regulator and to the throttled master.

## 6. Data & cohort design

**Source**: Hyperliquid public info API (`api.hyperliquid.xyz/info`), no auth, free. Verified endpoints (spike 2026-05-30):
- `userFillsByTime` — tick-by-tick fills (`closedPnl`, `px`, `sz`, `dir`, `startPosition`, `liquidation` key). Cap: 10k most recent fills/address.
- `portfolio` — accountValueHistory + pnlHistory (equity curve).
- `historicalOrders` — stop/trigger orders (`isTrigger`, `triggerPx`, `isPositionTpsl`, `reduceOnly`).
- `userNonFundingLedgerUpdates` — deposits/withdrawals (margin top-up behavior).

**Three cohorts, selected by outcome-blind rules to avoid hindsight bias:**
1. **Blow-up cohort** — masters whose accounts hit the §5.3 blow-up definition within the study window. Sourced from public liquidation trackers (CoinGlass, HyperTracker, thunderhead-stats `largest_liquidated_notional_by_user`) + known cases (James Wynn `0xBC47…`, March-2025 50x ETH whale). Target N ≥ 20 (more if feasible).
2. **Stable cohort** — masters active across the same window with no blow-up, selected by a rule fixed in advance (e.g., on a leaderboard at window-start, still solvent at window-end). Target M comparable to N.
3. **Volatility-null cohort/windows** — market-wide high-volatility periods (e.g., large BTC/ETH moves) used to prove the detector does NOT fire on stable traders merely because the market moved.

**Bias controls (first-class, this is what makes it rigorous):**
- **No look-ahead**: detector at time t uses only data ≤ t. Lead-time measured causally.
- **Outcome-blind cohort selection**: stable cohort chosen by a pre-window rule, never by "we know they survived."
- **Survivorship/selection honesty**: report how cohorts were enumerated; acknowledge known limits (we can't see masters who left no on-chain trace).
- **The 10k-fill cap caveat**: high-frequency masters (Wynn ≈ 12k fills/week) yield only ~1 week of history; lower-frequency masters yield long history. Reported per-trader; HFT-class handled by real-time capture or windowed analysis. Not a blocker.

## 7. Experimental design

- **Retrospective (Claim A)**: for each blow-up master, run detector causally; record lead-time = T(blow-up) − T(first sustained alert). Aggregate median + bootstrap CI. Compare vs equity-threshold-on-master baseline (lead-time ≈ 0) and vs naive baselines (random alert, simple-WR window).
- **Population/prospective-style (Claim B)**: across blow-up + stable + null cohorts, compute discrimination (AUC) and volatility-null FPR over the window.
- **Counterfactual (Claim C)**: post-alert avoided-loss × follower model → estimated protected AUM, with sensitivity range.
- **Mechanism appendix (synthetic)**: the existing synthetic/grid machinery demonstrates detector mechanics under controlled drift — **appendix only**, real retrospective is the main show.
- **Stats**: pre-registered thresholds; bootstrap CIs; explicitly address cross-trader/cross-time dependence (don't repeat the prior paper's inflated p-values); report effect sizes, not just p.

## 8. Paper structure (section outline)

1. Introduction — copy-trading contagion, the lead-time problem, contributions.
2. Related work — copy trading & ZuluGuard; behavioral/concept drift; changepoint/SPC; on-chain transparency.
3. The observability argument — why outcome-monitoring is too late for followers (MaxDDStop reframe).
4. Method — 3 axes, vol-normalization, continuous detector, composite alert, audit chain.
5. Data — Hyperliquid, cohorts, ground truth, bias controls.
6. Results — A (lead-time, headline) · B (discrimination) · C (follower-impact).
7. Negative results & boundaries — BOCPD/DQS DEAD, binary-CUSUM-vs-MaxDDStop, the 10k cap, what we can't see.
8. Discussion — deployment as broker control, regulatory fit, ZuluGuard contrast.
9. Conclusion.
Appendix — synthetic mechanism validation; reproducibility (code + queried addresses + timestamps).

## 9. How existing work is recycled (nothing wasted)

| Prior asset | New role |
|---|---|
| MaxDDStop-beats-CUSUM result | §3 motivation core (outcome-monitoring too late for followers) |
| BOCPD DEAD on sparse binary | §7 negative results; justifies continuous NIG/mSPRT choice |
| DQS zero-separation | §7 boundary: monitoring is strategy/account-level, not per-trade |
| SPC/CUSUM rigor + h-sensitivity | methods credibility; binary-CUSUM as a baseline |
| SSRT `mSPRT_t03` (Type-I<0.05) | candidate primary detector |
| SHA-256 audit chain | §5.4 auditability differentiator |
| OWM/memory layers | optional: stores the behavioral trajectory the detector reads |

## 10. Scope (YAGNI) & out-of-scope

**In**: Hyperliquid retrospective on real blow-up vs stable masters; 3-axis detector; lead-time/discrimination/impact; audit trail; synthetic appendix.

**Out (explicitly)**: retail trader journaling; HFT alpha; MiFID/compliance product framing; full SaaS/billing; live broker integration; LLM coaching; horizontal memory benchmarks (LoCoMo); multi-venue connectors. (All per pivot decision.)

## 11. Risks & open questions

- **R1 — Cohort size**: enough enumerable real blow-up masters with ≥ minimal history? *Mitigation*: spike confirmed rich per-address data; broaden via liquidation trackers; N≥20 target, report actual.
- **R2 — Follower data for Claim C**: CEX copy-follower counts not on-chain. *Mitigation*: GMX/Perpy on-chain copy vaults for a real-follower subset; else clearly-estimated model. C is framing, not a gate.
- **R3 — Selection/hindsight bias**: addressed via outcome-blind cohort rules + causal no-look-ahead (§6). Must be airtight or reviewers kill it.
- **R4 — 10k-fill cap** for HFT-class masters (§6). Report per-trader; not a blocker.
- **R5 — Detector tuning = overfit risk**: pre-register thresholds; hold out a test set of masters never seen during tuning.
- **Open**: exact K/H reporting units; AUC/FPR target values (set after a tuning-set dry run, before touching held-out test set); primary detector NIG vs mSPRT_t03 (decide on tuning set).

## 12. Build phases (after spec approval → writing-plans)

1. **Data pipeline** — Hyperliquid fetch/normalize (fills, portfolio, orders, ledger) → per-trader trajectory; cohort enumeration. (New code in `scripts/research/` or `research/`, **does not touch core MCP tools**.)
2. **Detector** — 3-axis vol-normalized features + continuous changepoint + composite sustained alert + audit-chain emit.
3. **Retrospective experiments** — Claims A/B/C on real cohorts; synthetic mechanism appendix.
4. **Writing** — assemble paper per §8; reproducibility appendix (addresses + query timestamps).
5. **Pre-submission** — LaTeX/figures/refs; arXiv metadata; CC-BY; submit timed for **Monday listing** (Sun ~13:55 ET = Mon ~01:55 Taiwan) per `behavioral-drift-paper-arxiv-2026-05.md`.

**Build constraints (codex+Opus consensus)**: branch `copytrading-drift-demo`; no edits to `src/tradememory/mcp_server.py`; sell lead-time/auditable/discrimination, never DD-reduction; real retrospective is the headline, synthetic is appendix; run pytest (1374 tests) green before any commit that touches `src/`.

---

*This spec is the blueprint. Implementation begins only after spec review + Sean's approval, via the writing-plans skill.*
