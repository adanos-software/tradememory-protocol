# Design Spec — Copy-Trading Blow-Up Early Warning Paper

> Status: DRAFT rev2 (hardened after adversarial review) · Date: 2026-05-30 · Author: Sean Peng (Syuan Wei Peng), Mnemox AI
> Supersedes the framing of `docs/research/arxiv-paper-behavioral-drift.md` (self-monitoring SPC paper).
> Strategic context: `COPYTRADING-PIVOT-RESUME.md` + memory `tradememory-crypto-drift-pivot-2026-05-28.md`.
> rev2 closes 4 review blockers: strawman baseline, survivorship/selection bias, label leakage, time-clustering. See §13 changelog.

---

## TL;DR（繁中，給 Sean 快掃）

把現有「self-monitoring CUSUM」論文 **reframe** 成旗艦：**在真實 Hyperliquid 鏈上資料上，偵測被跟單的 master trader 在「爆倉拖垮 follower」之前的行為漂移**。

- **Headline (A)**：偵測器 lead-time **贏過最強的非平凡早期 baseline**（槓桿百分位 tripwire / 回撤加速度 / 啟發式），事件叢集 CI 排除 0。**不是**跟「crater 才觸發」的門檻比（那是套套邏輯）。
- **Rigor (B)**：爆倉 vs 穩定 master 鑑別力（AUC），事件叢集 CI；市場級波動期不誤報；報 precision/PPV + 誤凍結成本曲線。
- **Impact (C)**：無量綱敏感度曲面（$saved / $follower-AUM / hour lead-time），**摘要不放單一 $ 數字**。
- **資料**：Hyperliquid 官方 API（spike 2026-05-30 驗證）。Frozen-at-T₀ universe，爆/穩由未來決定。名人（Wynn）只當 appendix case study，**不進統計**。
- **撼動世界的點**：真錢、真人、真爆、鏈上可驗證、預先註冊、抗 selection bias。不是 synthetic grid strategy。

---

## 1. Working title

**Primary**: *Early Warning of Copy-Trading Blow-Ups: Behavioral Drift Detection for Master Traders on On-Chain Perpetual Futures*

Alternatives: *Before the Liquidation: Lead-Time Detection of Master-Trader Behavioral Drift on Hyperliquid* · *Catching the Blow-Up Before It Spreads*.

Target venue: arXiv **q-fin.TR** (endorsement secured — Yijia Xiao, UCLA, 2026-05-20). Cross-list: cs.LG/cs.CE optional (needs category endorser).

---

## 2. The problem (institutional lens)

Copy trading lets thousands of *followers* mirror a *master* in real time. When a master's behavior degrades — over-leverage, abandoning stops, revenge margin top-ups — and they blow up, **followers blow up with them, simultaneously, with no time to react.** This is:

- **Documented & regulator-flagged**: IOSCO FR/06/2025 ("Online Imitative Trading Practices: Copy…"), UK FCA + CFTC 2025–2026 finfluencer/copy-trading warnings.
- **Unmeasured**: no vendor-neutral, transparent way for a broker to know *which master is about to blow up my followers*, early enough to act.
- **Partially solved, badly**: ZuluTrade's ZuluGuard auto-closes drifting signal providers — but **forex-only, single-venue, black box** (14 years, no transparency, no crypto).

Institutional readers (Bybit / Bitget / OKX / OTSO / BTSE risk lead, or a regulator) treat a paper as decisive only if it: (1) names a risk they can't currently measure, (2) proves it on real adversarial data, (3) quantifies money + lead-time, (4) yields a deployable control action, (5) is transparent/auditable. We target all five — but only (1)-(3) are *scientific claims*; (4)-(5) are deployment framing (§5.5), not evidence.

## 3. The reframe (why this beats the current paper)

The current paper asks: *can an agent monitor its own win rate to reduce its own drawdown?* Its headline: a trivial equity-drawdown threshold (**MaxDDStop**) beats the behavioral CUSUM detector in 93.5% of strategies. As a standalone, that tells an institution "behavioral monitoring isn't worth it."

**The copy-trading reframe inverts that result into the paper's motivation:**

> MaxDDStop wins **when you can observe your own equity in real time.** A follower **cannot observe the master's equity drawdown in time** — by the time an equity threshold fires, the follower has *already* taken the loss. The only way to gain *lead-time* is to detect **behavioral** drift in the master's observable order-flow **before** the equity crater.

The prior "failure" becomes the load-bearing argument. Nothing is wasted (§9).

## 4. Core claims & metrics (pre-registered, falsifiable)

**Pre-registration is real, not cosmetic (§7.2): the detector, its α, the baselines, the cohort-defining rules, and the metric targets are frozen in a timestamped git commit BEFORE the held-out test set is touched.**

### Claim A — Lead-time over non-trivial EARLY baselines (HEADLINE)
On held-out blow-up masters, the 3-axis detector raises its first guard-banded sustained alert a median of **Δ trades / hours EARLIER than the best of three non-trivial early baselines**:
- **B1 leverage-percentile tripwire** — fires when leverage crosses the trader's own historical p90 (self-referential, causal).
- **B2 drawdown-velocity** — fires on the *first derivative* of equity drawdown (acceleration), NOT the terminal level.
- **B3 heuristic** — "leverage up AND adding into a losing position," no changepoint math.
- (B0 terminal equity threshold / MaxDDStop-analogue is reported ONLY as the "too-late" reference with lead-time ≈ 0 by construction — explicitly NOT the headline comparator.)
- **Falsifiable failure**: if median lead-time advantage over best(B1,B2,B3) ≤ 0, or event-clustered CI includes 0, Claim A fails.

### Claim B — Discrimination (RIGOR)
Across the frozen-at-T₀ universe (§6), the detector separates *blows-up-within-Δ* from *does-not* with **AUC ≥ target**, with **event-clustered CIs** (§7.3); AND the **false-positive rate during market-wide volatility windows** (null cohort) stays below a pre-set bound; AND we report **precision/PPV and expected false-freeze rate at the operating threshold** plus a cost curve (cost of wrongful freeze vs AUM saved), because blow-ups are rare and AUC alone hides precision.
- **Falsifiable failure**: AUC CI lower bound ≤ 0.5+margin, or volatility-null FPR exceeds bound, or PPV at operating point below a pre-set floor.

### Claim C — Follower impact (IMPACT FRAME, not a stat claim)
Presented ONLY as a **dimensionless sensitivity surface**: "$ follower loss avoided per $1 follower AUM per hour of lead-time," across freeze-latency assumptions. **No single dollar figure in the abstract.** Real-follower grounding via on-chain copy vaults (GMX/Perpy) where available; otherwise an explicitly-labelled model with a sensitivity range. Lives in Discussion, not Results headline.

## 5. Method

### 5.1 Three orthogonal risk axes (vol-normalized, per-axis sign)
| Axis | Direction (bad) | Observables (verified API fields) |
|---|---|---|
| **Exposure** | ↑ | notional ÷ account value; size in ATR units; leverage creep |
| **Discipline** | ↓ | stop/trigger order presence rate (`isTrigger`/`isPositionTpsl`), holding-time, reduce-only behavior |
| **Tilt** | ↑ | margin top-up frequency/acceleration (`deposit` ledger), adding into losers, trade-frequency spikes |

Volatility normalization (size/equity or size/ATR) is mandatory — else we can't distinguish "raised the bet" from "market got volatile."

### 5.2 Detector (committed a priori — no peeking)
- **Per-axis one-sided sequential test** (mSPRT-style, sign-flipped per axis per §5.1), α **fixed from theory now** (mSPRT Type-I≈0.008 reference), NOT tuned on data.
- **Composite alert** = sustained simultaneous drift across axes, **Holm-corrected across the 3 axes**, requiring ≥ M consecutive windows. **M and the composite threshold are calibrated on SYNTHETIC Monte-Carlo data (not the real test set)** to hit a target composite Type-I/power, frozen before real held-out data.
- **A fresh 3-axis-composite Type-I/power MC is mandatory** — the single-stream mSPRT Type-I number does NOT transfer to the composite.
- Excluded as primary (DEAD/INVALID/wrong-tool in prior research, §9): binary CUSUM, BOCPD, DQS, anti-resonance gate, CalibratedAgent. **The paper's detector code path must strip the embedded binary-CUSUM remnants in `owm/changepoint.py` (`_cusum_s`, `_cusum_threshold`, `cusum_alert`) or rename them as baseline-only — else released code contradicts the paper.**

### 5.3 Guard band against label leakage (CRITICAL)
Exposure & Tilt are mechanically coupled to the equity curve, so an "early" alert could merely be reading a contemporaneous shadow of the crater used as the label. Firewall:
1. **Guard band**: a counted alert MUST fire while account value ≥ **X% of running peak** AND strictly **before the first liquidation fill of the terminal cascade**. Alerts inside the cascade window don't count as "early."
2. **Equity-decoupled ablation**: a **discipline-only** detector (stop-order presence + holding-time, no equity-derived feature) must show non-trivial lead-time survives — proving the signal isn't just the equity proxy.
3. Margin top-ups **inside** the terminal cascade are excluded from "early" Tilt signal.

### 5.4 Ground truth (forward-only, non-circular)
Blow-up event time **T defined causally, no hindsight**: first time cumulative drawdown from running peak exceeds a **pre-registered %** and does not recover within a **pre-registered horizon** (or first liquidation fill, whichever is earlier). The "inflection of the full curve" notion is rejected (uses future bars). Two-tier evidence both verified retrievable (spike 2026-05-30): `liquidation`-keyed fills (per-fill timestamp) + `portfolio` equity collapse.

### 5.5 Deployment framing (NOT a scientific contribution)
Auditable alert records (axis, statistic, evidence window, action) hashed into the SHA-256 linked audit chain → lets a broker defend a freeze to a regulator. This is the anti-ZuluGuard differentiator but lives in **Discussion/deployment**, never in the contributions list as evidence for A/B/C.

## 6. Data & cohort design (frozen-at-T₀ — kills selection bias)

**Source**: Hyperliquid public info API (`api.hyperliquid.xyz/info`), no auth. Verified endpoints (spike 2026-05-30): `userFillsByTime` (fills incl. `liquidation` key; 10k-most-recent cap), `portfolio` (equity), `historicalOrders` (stop/trigger), `userNonFundingLedgerUpdates` (margin deposits).

**Frozen universe (the anti-hindsight core):**
1. Pick a fixed historical date **T₀**. Snapshot the universe = all addresses on the Hyperliquid leaderboard / above a pre-set activity floor **at T₀**. Freeze this list.
2. Roll forward from T₀. **Blow-up vs stable is determined by the FUTURE**, not by trackers: a frozen-universe address that hits the §5.4 blow-up rule after T₀ = blow-up; one that doesn't = stable. **"Still solvent" is a measured outcome, never a selection filter.**
3. Report the **realized blow-up base rate** in the frozen universe (essential for precision/PPV, Claim B).
4. **Inclusion criterion**: minimum pre-event baseline length (≥ pre-registered trades/days before T) so the detector has a real baseline. **Disclose how many candidates this excludes** (itself a selection effect).
5. **Famous/notorious names (James Wynn `0xBC47…`, the March-2025 50x ETH whale, CoinGlass largest-liquidated) are NOT in the statistical cohort** (conditioning on notoriety = sampling on the dependent variable). They appear ONLY as a clearly-labelled **case-study appendix**, excluded from all AUC/lead-time statistics, pseudonymized facts only (§11 ethics).
6. **Volatility-null windows**: market-wide high-volatility periods used to prove the detector does NOT fire on stable traders merely because the market moved.

**Disclosed caveats**: 10k-fill cap couples history length to trade frequency (HFT masters → short baseline) → handled by the §6.4 minimum-baseline inclusion rule, with exclusions reported. On-chain crypto perps only (generalization scoped in §10).

## 7. Experimental design & statistics

### 7.1 Three-way split (locks pre-registration)
**Tuning set** (set features/M/threshold) → **validation set** (sanity) → **LOCKED test set** (reported as primary). Detector + α + baselines + metric targets frozen in a **timestamped git commit before the locked test is read**. Tuning/validation results reported as exploratory only.

### 7.2 What we measure
- **A (lead-time)**: per blow-up master, causal run; lead-time = T(blow-up) − T(first guard-banded sustained alert); advantage over best(B1,B2,B3); aggregate with event-clustered CI.
- **B (discrimination)**: AUC + volatility-null FPR + PPV/precision at operating point + cost curve, all event-clustered.
- **C (impact)**: dimensionless sensitivity surface (§4C).
- **Mechanism appendix (synthetic)**: controlled-drift demonstration of detector mechanics — appendix only.

### 7.3 Dependence handling (fixes the prior paper's inflated p)
Blow-ups **cluster in time** (one BTC/ETH crash liquidates many masters the same hour), so naive N (#traders) ≫ effective N (#independent market events). Therefore:
- **Block / cluster-robust bootstrap clustering by liquidation-DAY (market event)**, not by trader.
- Report **effective sample size = number of independent crash clusters**.
- **Leave-one-event-out** robustness check.
- All CIs reported under event-clustered resampling, never i.i.d.-by-trader.

## 8. Paper structure
1. Intro — copy-trading contagion, lead-time problem, contributions (= A lead-time, B discrimination, C impact-frame). 2. Related work — copy trading & ZuluGuard; behavioral/concept drift; changepoint/SPC; on-chain transparency. 3. Observability argument (MaxDDStop reframe). 4. Method — 3 axes, detector, guard band, ground truth. 5. Data — Hyperliquid, frozen universe, cohorts, bias controls. 6. Results — A · B (+precision/cost) · C. 7. Negative results & boundaries — BOCPD/DQS DEAD, binary-CUSUM-vs-MaxDDStop, 10k cap, what we can't see. 8. Discussion — deployment (audit chain), regulatory fit, ZuluGuard contrast, ethics. 9. Conclusion. Appendix — case studies (Wynn et al., facts only), synthetic mechanism, reproducibility (archived raw API responses + query timestamps + commit hashes).

## 9. How existing work is recycled (nothing wasted)
| Prior asset | New role |
|---|---|
| MaxDDStop-beats-CUSUM | §3 motivation core (outcome-monitoring too late for followers); B0 "too-late" reference |
| BOCPD DEAD on sparse binary | §7 negative results; justifies continuous detector choice |
| DQS zero-separation | boundary: monitoring is account-level, not per-trade |
| SPC/CUSUM rigor + h-sensitivity | binary-CUSUM as a baseline; methods credibility |
| SSRT mSPRT (Type-I<0.05) | per-axis sequential test basis (composite re-validated fresh) |
| SHA-256 audit chain | §5.5 deployment differentiator (NOT a scientific claim) |

## 10. Scope (YAGNI) & out-of-scope
**In**: Hyperliquid retrospective, frozen-universe cohorts, 3-axis detector, lead-time/discrimination/impact, guard-band + decoupled ablation, synthetic appendix. Empirical claims **scoped explicitly to on-chain crypto perpetuals**; forex/equity copy desks = future work (no implied transfer).
**Out**: retail journaling; HFT alpha; MiFID/compliance product framing; full SaaS/billing; live broker integration; LLM coaching; horizontal memory benchmarks; multi-venue connectors.

## 11. Ethics & reproducibility
- **Pseudonymize** the statistical cohort. Case-study addresses only if publicly self-doxxed (e.g., an influencer); stick to **observable facts** (leverage, liquidation), avoid psychological labels about identifiable persons; add a **data-ethics statement**. Note the COI (authors sell the monitoring product) explicitly.
- **Archive raw API responses with query timestamps** (the 10k-window rolls, so live re-query is non-reproducible); pin the dataset; release code + queried addresses + commit hashes.

## 12. Risks & open questions
- **R1 cohort size / base rate**: frozen universe must yield enough post-T₀ blow-ups AND enough independent crash *events* (effective N). Mitigation: choose T₀ to span ≥ several distinct volatility regimes; report effective N honestly; if too few events, widen window/universe.
- **R2 follower data (C)**: CEX follower counts off-chain → on-chain copy vaults subset + labelled model; C is framing not a gate.
- **R3 label leakage**: §5.3 guard band + decoupled ablation must be airtight or reviewers kill it.
- **R4 detector novelty vs single-stream mSPRT**: 3-axis composite needs its own MC validation; don't inherit numbers.
- **Open**: T₀ date; activity floor; baseline-length minimum; drawdown % + recovery horizon for T; X% guard-band; AUC/PPV targets — **all fixed on tuning/synthetic before locked test, in writing.**

## 13. rev2 changelog (what the adversarial review changed)
- Headline baseline: crater-threshold (trivial) → best of non-trivial **early** baselines B1/B2/B3.
- Cohort: tracker/notoriety-seeded + "still-solvent" filter → **frozen-at-T₀ universe**, outcome determined by future; famous names → appendix only, excluded from stats.
- Added **§5.3 guard band + equity-decoupled ablation** against label leakage.
- Ground-truth T: hindsight "inflection" → **forward-only drawdown rule**.
- Stats: i.i.d.-by-trader → **event-clustered (by liquidation-day) bootstrap + effective N + leave-one-event-out**.
- Pre-registration: targets-after-peeking → **3-way split, frozen in timestamped commit before locked test**.
- Detector: strip binary-CUSUM remnants from paper code path; **fresh 3-axis composite Type-I/power MC**; per-axis sign.
- Added **precision/PPV + false-freeze cost curve** (base-rate honesty).
- Claim C: single $ figure → **dimensionless sensitivity surface**, no $ in abstract.
- Audit chain moved from contributions → **deployment/discussion**.
- Added **ethics (pseudonymization, COI) + reproducibility (archived raw responses)**; scoped empirical claims to crypto perps.

## 14. Build phases (after spec approval → writing-plans)
1. **Data pipeline** — Hyperliquid fetch/normalize + frozen-universe enumeration at T₀ + raw-response archive. (New code in `scripts/research/` or `research/`; **does not touch `src/tradememory/mcp_server.py`**.)
2. **Detector** — 3-axis vol-normalized features + per-axis sequential test + Holm-corrected sustained composite + guard band + audit-emit; fresh composite MC calibration on synthetic.
3. **Pre-registration commit** — freeze detector/α/baselines/targets/cohort rules; timestamp.
4. **Experiments** — A/B/C on locked test; decoupled ablation; event-clustered stats; synthetic mechanism appendix.
5. **Writing** — assemble per §8; reproducibility appendix.
6. **Pre-submission** — LaTeX/figures/refs; arXiv metadata; CC-BY; submit for **Monday listing** (Sun ~13:55 ET = Mon ~01:55 Taiwan) per `behavioral-drift-paper-arxiv-2026-05.md`.

**Build constraints**: branch `copytrading-drift-demo`; no edits to core MCP tools; sell lead-time/auditable/discrimination, never DD-reduction; real retrospective is headline, synthetic is appendix; pytest (1374 tests) green before any `src/` commit.

---

*Blueprint only. Implementation begins after spec review + Sean's approval, via writing-plans.*
