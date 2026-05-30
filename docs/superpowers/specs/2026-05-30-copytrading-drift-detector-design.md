# Design Spec — Plan 2: 3-Axis Behavioral Drift Detector + Synthetic Calibration

> Status: DRAFT · Date: 2026-05-30 (UTC) · Author: Sean Peng (Syuan Wei Peng), Mnemox AI
> Branch: `copytrading-drift-demo`
> Parent spec: `docs/superpowers/specs/2026-05-30-copytrading-drift-paper-design.md` (refines §5.1–§5.3, §7).
> Pre-registration: `research/hyperliquid/PRE-REGISTRATION-DRAFT.md` — Part 1 LOCKED (commit `92e343c`); **this spec produces the artifacts that let Part 2 lock.**
> Plan 1 (data pipeline) BUILT: `research/hyperliquid/` package, 23 tests green (`python -m pytest research/hyperliquid/tests/`).

---

## TL;DR（繁中，給 Sean 快掃）

把上一篇論文設計裡「偵測器」這塊**做成程式 + 在合成假資料上調好參數鎖死**。三條軸抓高手走鐘：**Exposure（下注變大）↑ / Discipline（不守紀律）↓ / Tilt（上頭梭哈）↑**。每條軸用既有、已被 22,500 次 MC 驗證過的 mSPRT 引擎跑 sequential test，三條軸用 Holm 校正合成一個「持續 ≥ M 格才喊」的 composite 警報。

**防作弊三件套全寫進去**：(1) guard band — 只有帳戶還活著（≥70% 高點）且第一筆強平之前喊的才算「提早」；(2) 參數只在合成假資料上調（HMM 兩態生成器），絕不碰真實 cohort（防 data snooping）；(3) ablation — 證明只看 Discipline 一條軸也能保住一半 lead-time。

**Plan 2 不碰真實資料。** Plan 2 結束時：偵測器程式 + 合成校準鎖出一組參數 → 鎖進 pre-registration Part 2 的 timestamped commit → 之後 Plan 3 才拿這組鎖死的偵測器去真實資料跑。

**硬約束**：branch `copytrading-drift-demo`；不碰 `src/tradememory/mcp_server.py`；偵測器程式 + tests 放 `research/hyperliquid/detector/`、隔離在主 1374-suite 之外；UTC；commit 完直接 push；每個 commit 後更新 CLAUDE.md。

---

## 1. Scope

**IN (this plan):**
- The detector code path under `research/hyperliquid/detector/`: per-trade behavioral primitives → per-bucket per-axis observations → per-axis sequential test → Holm composite + sustained-M → guard band → alert stream.
- A 2-state HMM synthetic master generator (label-blind, anchored on the tuning split).
- A calibration harness that grid-searches detector hyperparameters on synthetic data to hit pre-registered Type-I/power targets and emits one frozen hyperparameter tuple.
- An ablation harness (discipline-only mode) with a synthetic sanity check that the ≥50% lead-time bar is measurable.
- An in-place rename of the legacy binary-CUSUM remnants in `src/tradememory/owm/changepoint.py` so released code does not contradict the paper.
- The artifacts (frozen hyperparameter values) needed to lock pre-registration Part 2 in a timestamped commit.

**OUT (deferred to Plan 3):**
- Running the detector on the real frozen-universe cohort.
- The A/B/C experiments, event-clustered statistics on real data, real-cohort ablation.
- The follower-impact model (Claim C), case studies, paper writing.
- Any change to `mcp_server.py`, REST endpoints, or MCP tool surface beyond the CUSUM rename.

**Non-goal:** a production detector. This is research code for a retrospective paper. Simplicity over generality.

---

## 2. Locked design decisions (from this session's brainstorming)

| # | Decision | Choice |
|---|---|---|
| D1 | Window / observation cadence | **Hybrid**: primitives update per-fill (internal state); the sequential test consumes ONE observation per axis at each bucket close, using the carry-forward latest value if the bucket had no fill. |
| D2 | Bucket length | **Grid-searched in synthetic MC** over {1h, 4h, 24h}; calibration picks ONE to freeze as primary, the other two become robustness reruns. |
| D3 | Per-axis null (mSPRT baseline) | **James-Stein hybrid**: `μ_blend = w(n)·μ_self + (1−w(n))·μ_universe`, `w(n)=n/(n+κ)`. Short-history masters shrink toward the cross-sectional (tuning-split) median; long-history masters use their own pre-T₀ baseline. Same blend for σ via inverse-variance weights. |
| D4 | Per-axis observation construction | **Per-axis composite with synthetic-MC-tuned weights**: each axis = weighted sum of its z-scored primitives; the per-axis weight vector is fit on synthetic (Fisher-LDA separating Drifting vs Normal within the axis), frozen into pre-reg before the locked test. |
| D5 | Synthetic generator | **2-state HMM** (Normal ↔ Drifting); emissions = marginal-anchored multivariate Gaussian (anchors from tuning split, labels unused); Drifting state shifts per-axis means by δ in the bad direction. |
| D6 | Legacy `owm/changepoint.py` CUSUM | **Rename in place**: `_cusum_*` → `_legacy_cusum_*`; `ChangePointResult.cusum_alert/cusum_value` kept as fields with a `legacy_`-aliased docstring stating "pre-pivot, not part of the paper detector." Full 1374-suite must stay green. |
| D7 | Ablation scope in Plan 2 | **Define + synthetic sanity check**: write the discipline-only ablation harness and verify on synthetic (3 ground-truth drift scenarios) that the ≥50% lead-time bar is reliably measurable with event-clustered CI. Real-cohort ablation is Plan 3. |

These supersede any conflicting reading of parent-spec §5.2 and become the pre-reg Part 2 values once the calibration run fixes the numeric grid winners.

---

## 3. Module architecture & import boundary

```
research/hyperliquid/detector/
  __init__.py
  primitives.py     # per-trade behavioral state machines → per-bucket primitive values
  axis.py           # z-score (shrinkage null) + weighted-sum compose → 3 per-axis observations
  shrinkage.py      # James-Stein blend of self vs universe baseline (μ, σ)
  sprt_axis.py      # per-axis wrapper around MixtureSPRT: sign convention + (null=0, σ=1) on z-scored input
  composite.py      # Holm step-down across 3 axis p-values + sustained-M counter
  guard_band.py     # is_early(t, addr): equity ≥ X%·peak AND t < first liquidation fill
  detector.py       # orchestration: Trajectory → bucketed observations → guarded alert stream
  hmm_synth.py      # 2-state HMM synthetic master generator (label-blind)
  calibration.py    # grid search over (bucket, M, τ, weights, κ) on synthetic → frozen tuple
  ablation.py       # discipline-only mode + synthetic sanity harness
research/hyperliquid/tests/detector/
  test_primitives.py  test_shrinkage.py  test_axis.py  test_sprt_axis.py
  test_composite.py   test_guard_band.py  test_detector.py
  test_hmm_synth.py   test_calibration.py test_ablation.py
  test_no_owm_imports.py   # CI guard: detector/ must not import tradememory.owm.*
```

**Import rule for `research/hyperliquid/detector/**`** — may import ONLY:
- Python stdlib + `math` (zero heavy deps, matching Plan 1 style).
- `research.hyperliquid.{models, normalize, trajectory, blowup}` (Plan 1 primitives).
- `tradememory.ssrt.core.MixtureSPRT` (reuse the MC-validated engine; do NOT reimplement).
- **MUST NOT import `tradememory.owm.*`** — the paper detector is not the legacy CUSUM/BOCPD/DQS path. Enforced by `test_no_owm_imports.py` (AST scan of the detector package).

**Test isolation:** detector tests live under `research/hyperliquid/tests/detector/` and run via `python -m pytest research/hyperliquid/tests/`. The main suite (`python -m pytest tests/`) is touched ONLY by the D6 CUSUM rename, which must keep it at 1374 passing.

---

## 4. Per-trade primitives (`primitives.py`)

Each axis exposes a small set of primitives. All are computed from Plan 1's `Trajectory` (fills, equity, ledger, orders) and are vol-normalized so we distinguish "raised the bet" from "the market got volatile."

| Axis | Primitive | Definition (from verified API fields) | Sign (bad) |
|---|---|---|---|
| **Exposure** | `leverage` | `abs(notional_after_fill) / equity_at_fill` (notional from running signed position × px) | ↑ |
| | `notional_growth` | per-bucket Δ\|position\| ÷ equity | ↑ |
| | `size_in_sigma` | fill `sz` ÷ rolling-14d realized return std of that coin | ↑ |
| **Discipline** | `stop_attach_rate` | fraction of opening fills that have a live trigger/TP-SL order concurrently (`isTrigger`/`isPositionTpsl` from `historicalOrders`) | ↓ |
| | `reduce_only_rate` | fraction of fills that shrink \|position\| (inferred from `startPosition` + signed `sz`) | ↓ |
| | `mean_hold_hours` | mean closed-position lifetime in the bucket | ↓ (very short = churn) |
| **Tilt** | `topup_count` | count of `deposit`-type ledger events in the bucket (`userNonFundingLedgerUpdates`) | ↑ |
| | `loser_add_count` | count of fills that increase \|position\| while the position carries unrealized loss vs avg entry | ↑ |
| | `fill_rate_spike` | bucket fill count ÷ trailing-24h mean fill count | ↑ |

**Cadence (D1):** each primitive is a per-trade state machine updated on every fill; at each bucket close the detector reads the current value (carry-forward the last value if the bucket had no fill, EXCEPT counts like `topup_count`/`loser_add_count`/`fill_rate_spike` which are per-bucket aggregates resetting each bucket).

**Edge cases each primitive must handle (TDD targets):** zero-equity bucket (skip / NaN-guard), no fills before T₀ (handled upstream by Plan 1 `meets_baseline`), coins with <14d history for `size_in_sigma` (fall back to cross-coin pooled std), divide-by-zero in `fill_rate_spike` when trailing mean is 0 (emit 0).

---

## 5. Axis observation (`axis.py` + `shrinkage.py`)

Per bucket, per axis:

1. **Compute** each primitive value (§4).
2. **Shrinkage null (D3):** z-score each primitive against
   - `μ_blend = w(n)·μ_self + (1−w(n))·μ_universe`, `w(n) = n/(n+κ)`
   - `σ_blend` from inverse-variance combination of `σ_self`, `σ_universe`
   - `n` = count of pre-T₀ baseline observations for that primitive; `μ_self/σ_self` from the master's pre-T₀ trajectory; `μ_universe/σ_universe` from the **tuning-split** cross-sectional distribution (never the locked test).
   - `κ` (shrinkage strength) is grid-searched (§7).
3. **Weighted compose (D4):** `y_axis = Σ_i ω_{axis,i} · z_i` with `Σ_i |ω_{axis,i}| = 1`. The weight vector `ω_axis` is Fisher-LDA-fit on synthetic (§6) to best separate Drifting from Normal within the axis, frozen before the locked test.
4. **Sign convention for mSPRT** (the engine flags evidence that the running mean drifts **below** null): feed `−y_Exposure` and `−y_Tilt` (bad↑ → negative), and `+y_Discipline` (bad↓ → already negative). After this flip, "drift in the bad direction" is always "mean below 0" for all three streams.

Because inputs are z-scored, the per-axis `MixtureSPRT` is constructed with `null_mean=0`, `sigma=1`; only `tau`, `alpha`, `burn_in` vary.

---

## 6. Detector pipeline (`sprt_axis.py`, `composite.py`, `guard_band.py`, `detector.py`)

**Per-axis sequential test (`sprt_axis.py`):** a thin wrapper that constructs `MixtureSPRT(alpha=0.01, tau=τ_axis, sigma=1, null_mean=0, burn_in=B)` and feeds the signed z-scored observation each bucket. Returns the always-valid p-value (`SSRTVerdict.p_value`). `alpha=0.01` per axis re-affirms pre-reg Part 2 #12 (mSPRT Type-I ≈ 0.008, 22,500 MC).

**Composite (`composite.py`):**
- At each bucket close, collect the 3 per-axis p-values.
- **Holm step-down across the 3 axes**: sort `p_(1) ≤ p_(2) ≤ p_(3)`; the composite "fires" this bucket iff `p_(1) ≤ α/3` (= 0.00333 at α=0.01). Step-down ordering is retained to attribute which axis carried the alert (reporting only).
- **Sustained counter**: increment on a firing bucket, reset to 0 on a miss. Raise a **composite alert** at the first bucket where the counter reaches **M**.
- `M` is grid-searched on synthetic (§7).

**Guard band (`guard_band.py`, D3 anti-leakage):**
```
is_early(t, addr) = (equity[t] / running_peak[t] ≥ X) AND (t < first_liquidation_fill_time(addr))
```
with `X = 0.70` (pre-reg Part 1 §14 / Part 2 #14). Alerts are always emitted, but those with `is_early == False` are flagged `late` and excluded from lead-time statistics. The detector therefore returns a stream of `(bucket_time, fired, alert_raised, is_early, carrying_axis)` records.

**Orchestration (`detector.py`):** `Trajectory + baseline_stats + hyperparams → alert stream`. Pure function (no I/O, no DB), deterministic given inputs — so it is identical when run on synthetic streams (§6 HMM) and on real trajectories (Plan 3).

---

## 7. Synthetic generator (`hmm_synth.py`) — label-blind

**Anchoring (labels NOT used):** from the **tuning split** (40% of addresses, seed-fixed, event-clustering respected) compute, per primitive: median, MAD, AR(1) coefficient; and the 9×9 cross-primitive rank-correlation matrix (projected to PSD). These define the emission distribution. No outcome/blow-up label enters the generator — only the marginal/covariance shape of real behavior.

**States & emissions:**
- 2-state HMM: `Normal` and `Drifting`.
- Each state's per-primitive mean = anchored marginal mean + a state shift; covariance = anchored cov.
- `Normal`: shift = 0 for all 9 primitives.
- `Drifting`: shift = `δ · sign(bad_direction)` per primitive (single magnitude δ per axis). **δ ∈ {0.5, 1.0, 1.5} MAD** is a reported grid (power-by-δ curve), with **δ = 1.0 the primary**.

**Transitions / suites:**
- **Type-I suite** (false-alarm calibration): pure-`Normal` streams (`θ_onset = 0`). Type-I = fraction of streams that ever raise a composite alert.
- **Power suite**: each stream has exactly ONE onset at a uniformly-random bucket (clean lead-time ground truth); `θ_persist ∈ {0.95, 0.99}` controls drift duration. Power = fraction of Drifting streams alerted; lead-time = `T_alert − T_onset` in buckets × bucket-hours.

**Stream length:** matched to the real window (11 months) at the candidate bucket length (≈ 8030 buckets @1h, 2007 @4h, 334 @24h). **N = 10,000 synthetic masters per grid cell.**

**Transfer assumption (stated honestly for the reviewer):** weights/M/threshold tuned on synthetic transfer to the real cohort only insofar as the real tuning-split marginal/cov structure resembles the locked-test structure. Mitigations: δ is a reported grid (not tuned); a robustness rerun uses Student-t innovations to probe heavy-tail sensitivity; the generator's anchors come from real tuning-split behavior, not invented parameters.

---

## 8. Calibration harness (`calibration.py`)

**Joint grid:**
- `bucket ∈ {1h, 4h, 24h}` (D2)
- `M ∈ {2, 3, 4, 6, 9, 12}`, constrained so `6h ≤ M·bucket ≤ 7d`
- per-axis `τ ∈ {0.3, 1.0}` (0.3 = SSRT default)
- per-axis weights `∈ {equal-weight, Fisher-LDA}` (LDA fit on Normal vs Drifting synthetic within each axis)
- shrinkage `κ ∈ {7, 14, 30}` buckets

**Targets (pre-reg Part 2 #13, refined):** `power ≥ 0.70 AND composite Type-I ≤ 0.02`. Type-I budget 0.02 is the tight target given the projected base rate (~0.05–0.07) and the PPV ≥ 0.30 gate; if NO tuple passes at 0.02, relax to the pre-registered ceiling **0.05** and record that the relaxation occurred.

**Pickup rule (deterministic, recorded):** among passing tuples, rank by
1. highest power, then
2. shortest minimum-credible lead-time `M·bucket_hours` (smaller sells stronger), then
3. fewest total hyperparameter "degrees of freedom" (Occam tiebreak).
The winning tuple is the frozen primary; the other two bucket lengths' best tuples are kept as robustness reruns.

**Output:** a JSON artifact (`research/hyperliquid/detector/calibration_result.json`) with the full grid results, the winning tuple, realized Type-I/power, and the power-by-δ curve — the evidence cited when pre-reg Part 2 locks.

---

## 9. Ablation harness (`ablation.py`) — define + synthetic sanity (D7)

**Discipline-only mode:** run the detector with Exposure and Tilt axes masked (their per-axis p-value forced to 1.0 every bucket), so only the Discipline axis can carry the Holm composite.

**Synthetic sanity scenarios** (ground truth known because we set the Drifting shift):
- **A — discipline-only drift:** only Discipline-axis primitives shift in Drifting.
- **B — full 3-axis drift:** all 9 primitives shift.
- **C — exposure+tilt only:** the complement of A.

**Plan-2 pass criterion (locked):** under Scenario A, the discipline-only detector recovers **≥ 50%** of the full detector's median lead-time, with an event-clustered CI (resampling over synthetic onset-day clusters) that **excludes 0**. This proves the harness has the statistical power to *measure* the 50% bar — the real-cohort ablation (the actual Claim-A-supporting result) runs in Plan 3 against the same bar.

---

## 10. Legacy CUSUM rename (`src/tradememory/owm/changepoint.py`, D6)

**Before touching anything:** `grep` the repo for `cusum_alert`, `cusum_value`, `_cusum_` across `src/`, `tests/`, REST/MCP surfaces to enumerate consumers. If any public MCP/REST response exposes these, keep the public field name unchanged (alias) and rename only the private internals.

**Rename:**
- Private: `_cusum_s → _legacy_cusum_s`, `_cusum_threshold → _legacy_cusum_threshold`, `_cusum_target_wr → _legacy_cusum_target_wr`, `_cusum_wins → _legacy_cusum_wins`, `_cusum_total → _legacy_cusum_total`. Update `get_state`/`from_state` to read both new and old JSON keys (backwards-compat for persisted state).
- Public: keep `ChangePointResult.cusum_alert` and `cusum_value` field NAMES (backwards-compat), but update the module + class docstrings: *"Legacy binary-CUSUM, retained for backwards compatibility with pre-2026-05-30-pivot research. NOT part of the copy-trading drift paper detector (`research/hyperliquid/detector/`), which uses a per-axis mSPRT composite."*

**Verification gate:** `python -m pytest tests/ -x -q` stays at **1374 passing** after the rename. This is the ONLY `src/` change in Plan 2.

---

## 11. Data flow (end to end)

```
Plan 1 Trajectory (fills, equity, ledger, orders)
   │  baseline_stats(self pre-T₀) + universe_stats(tuning split)
   ▼
primitives.py   per-fill state → per-bucket 9 primitive values (carry-forward / per-bucket counts)
   ▼
shrinkage.py    James-Stein μ/σ blend (self ↔ universe by w(n)=n/(n+κ))
   ▼
axis.py         z-score → Fisher-LDA weighted sum → 3 axis observations → sign flip
   ▼
sprt_axis.py    MixtureSPRT(α=0.01, τ, null=0, σ=1) per axis → 3 always-valid p-values  (reuses tradememory.ssrt)
   ▼
composite.py    Holm step-down (fire iff p_(1) ≤ α/3) → sustained-M counter → composite alert
   ▼
guard_band.py   is_early = equity ≥ 0.70·peak AND before first liquidation fill
   ▼
detector.py     alert stream: (bucket_time, fired, alert_raised, is_early, carrying_axis)
```

The SAME `detector.py` consumes HMM synthetic streams (§7) for calibration/ablation and real `Trajectory` objects in Plan 3 — identical code path, which is what makes the synthetic calibration a valid pre-commit.

---

## 12. Testing strategy (bite-sized TDD)

Each module gets its own test file written test-first. Representative cases:
- **primitives:** known fill sequence → expected leverage/stop-rate/topup count; zero-equity, no-pre-history, single-coin edge cases.
- **shrinkage:** `n=0` → all universe; `n→∞` → all self; σ inverse-variance combine; κ monotonicity.
- **axis:** sign flip correctness (Exposure/Tilt negative when bad); weighted-sum normalization; LDA weight application.
- **sprt_axis:** drift-down series → p-value falls below α; flat series → p stays high; reuses `MixtureSPRT` (no engine reimplementation).
- **composite:** Holm fire threshold; sustained counter increments/resets; alert at M-th consecutive fire.
- **guard_band:** alert below 70% peak flagged late; alert after first liquidation flagged late; alert while healthy + pre-liq flagged early.
- **detector:** end-to-end on a hand-built drifting trajectory → early alert before constructed T.
- **hmm_synth:** Normal stream stationary stats match anchors; Drifting stream shifts by δ; single-onset placement; seed determinism.
- **calibration:** grid enumeration shape; pickup-rule tie-break ordering; target gate logic (pass/relax/record).
- **ablation:** discipline-only masking forces other axes to p=1; Scenario A lead-time fraction computed; CI-excludes-0 logic.
- **no_owm_imports:** AST scan asserts `detector/` imports no `tradememory.owm.*`.

All detector tests isolated under `research/hyperliquid/tests/detector/`. Determinism: any randomness (synthetic, splits) uses an explicitly passed seed (no `Math.random`/wall-clock).

---

## 13. Pre-registration Part 2 — fields this plan freezes

After the §8 calibration run, lock these in a timestamped commit on `copytrading-drift-demo` (the successor to `92e343c`), published as the Part-2 hash in the paper, BEFORE the locked test is read:

- Per-axis primitive lists (§4, frozen) + per-axis Fisher-LDA weight vectors
- Bucket length (the single grid winner) + per-axis `τ`
- Shrinkage formula + `κ`; burn-in `B` per master
- Composite `M`; Holm step-down rule (fire iff `p_(1) ≤ α/3`); per-axis `α = 0.01`
- Guard-band `X = 0.70`; ablation pass bar `≥ 50%` lead-time
- HMM anchoring procedure (label-blind, tuning-split marginals + Spearman cov); transition params (`θ_onset`, `θ_persist`) for Type-I and Power suites; primary `δ = 1.0` (+ {0.5, 1.5} robustness)
- Calibration pickup rule + realized Type-I/power; stream length / N per cell
- Random seeds (synthetic + tuning/validation/test address split)

---

## 14. Risks & open questions

- **R1 synthetic transfer (primary risk of the HMM route):** tuned weights/M assume tuning-split structure ≈ locked-test structure (§7). Mitigation: δ reported as a grid not tuned; Student-t robustness rerun; anchors are real (not invented). If the locked-test base rate or marginal shape diverges sharply, the paper reports the gap as a named limitation.
- **R2 carry-forward autocorrelation:** the hybrid cadence (D1) injects serial correlation across buckets with no new fills. The composite Type-I MC measures this directly (synthetic streams have the same carry-forward), so the calibrated M absorbs it — but the spec must keep carry-forward identical in synthetic and real paths.
- **R3 Fisher-LDA degeneracy:** if within-axis primitives are near-collinear, LDA weights blow up. Mitigation: ridge-regularize the within-class scatter; fall back to equal-weight if conditioning fails (the grid already includes equal-weight as a candidate).
- **R4 owm rename breakage:** the 1374-suite or a persisted-state consumer may depend on the private names. Mitigation: grep-first, alias public fields, dual-read JSON keys, gate on full suite green.
- **Open (resolved only by the calibration RUN, not pre-set):** the winning bucket/M/τ/weights/κ tuple — these are OUTPUTS of §8, fixed by the deterministic pickup rule, then frozen.

---

## 15. Build phases (after spec approval → writing-plans)

1. **primitives + shrinkage** (per-trade state machines, James-Stein blend) — TDD, isolated tests.
2. **axis + sprt_axis** (compose, sign, mSPRT wrapper reusing `tradememory.ssrt`).
3. **composite + guard_band + detector** (Holm, sustained-M, guard predicate, orchestration) — end-to-end synthetic-trajectory test.
4. **hmm_synth** (label-blind 2-state generator, anchored, seeded).
5. **calibration** (grid search, target gate, pickup rule, JSON artifact).
6. **ablation** (discipline-only mode + Scenario A/B/C synthetic sanity).
7. **owm CUSUM rename** (grep-first, rename, alias, dual-read; full 1374-suite green).
8. **Pre-registration Part 2 commit** (freeze §13 values from the calibration artifact; timestamped; update CLAUDE.md).

**Build constraints:** branch `copytrading-drift-demo`; no edits to core MCP tools (only the §10 rename in `owm/changepoint.py`); detector code + tests isolated in `research/hyperliquid/`; the real locked test is NOT read in Plan 2; UTC everywhere; `python -m pytest research/hyperliquid/tests/` green per commit, `python -m pytest tests/` 1374-green after the rename; commit + push each phase; update CLAUDE.md after each commit.

---

*Blueprint only. Implementation begins after spec review + Sean's approval, via writing-plans.*
