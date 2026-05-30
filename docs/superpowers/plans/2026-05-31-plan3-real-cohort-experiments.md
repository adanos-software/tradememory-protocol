# Plan 3 — Real-Cohort Experiments & Paper (implementation plan)

> Date: 2026-05-31 (UTC) · Branch `copytrading-drift-demo` · Spec: `docs/superpowers/specs/2026-05-30-copytrading-drift-paper-design.md` + `2026-05-30-copytrading-drift-detector-design.md`
> Pre-reg: `research/hyperliquid/PRE-REGISTRATION-DRAFT.md` (Part 1 LOCKED `92e343c`; Part 2 locks in this plan).
> Plan 2 (detector machinery) COMPLETE: `research/hyperliquid/detector/`, 154 tests, final review SHIP-READY + firewall PASS.

**Goal:** Take the frozen Plan-2 detector to a falsifiable result on real Hyperliquid data — compute the real tuning-split, lock pre-reg Part 2, run Claim A (lead-time) / B (discrimination) / C (impact-frame) on the locked test, and assemble the arXiv paper.

**Irreversibility gate:** Once the locked test cohort is read for A/B/C, the pre-registration is spent. **The Part-2 lock commit (Phase 7) and the locked-test read (Phase 8) are HUMAN-GATED — Sean presses the button, not an unattended run.** Everything before Phase 7 is reversible / outcome-blind and can be automated.

---

## Tonight's scaled-provisional run (NOT the pre-reg run)

To give an end-to-end "full picture" without spending the pre-registration, tonight runs a SCALED INDICATIVE pipeline on a ~1.2k-address sample (`universe_addrs.txt`, ≥$25k leaderboard universe, spread across ranks):
- **Stage 1 (running, `stage1_label.py`):** equity-only labeling on the sample → real base rate, blow-up cohort, crash-day histogram, idiosyncratic count, effective-N. Cheap (portfolio-only, reaches pre-T0 even under the 10k-fill cap).
- **Stage 2:** full trajectory (fills/orders/ledger) on the labeled cohort → behavioral primitives → real tuning-split marginals (anchors + cov).
- **Provisional calibration + holdout demo:** run the real-anchor calibration → indicative winner; run the detector on a VALIDATION holdout (never the locked test) → indicative Claim-A lead-time vs baselines.
- Everything labelled PROVISIONAL. The full-universe pre-reg run + Part-2 lock + locked-test read stay for Sean.

---

## Phases

### Phase 1 — Cohort (Stage 1 + Stage 2)
- **1a Stage-1 equity labeling** (`stage1_label.py`, scaled) — DONE tonight; full-universe version = same script over the full leaderboard (throttled, resumable). Exit: `cohort_stage1.json` with base rate, crash-day histogram, idiosyncratic vs market-event tagging (τ=3%), effective-N.
- **1b Stage-2 behavioral fetch** — for the labeled cohort (all blow-ups + a seed-fixed matched stable sample), fetch fills/orders/ledger, `build_trajectory`, apply `meets_baseline(≥50 fills, ≥14d pre-T0)`. Report the 10k-cap truncation count as the named selection-bias line. Exit: per-master `Trajectory` objects + the behavioral cohort.

### Phase 2 — Split (tuning / validation / locked-test)
- 40% tuning / 20% validation / 40% locked-test, seed-fixed BY ADDRESS with event-clustering respected (no crash-day leaks across splits). Pre-reg Part 4. The locked-test split is SEALED — not read until Phase 8.

### Phase 3 — Real baseline builder (makes κ live; SNR alignment)
- `build_real_baseline(cohort)`: per-master SELF stats from its own pre-T0 trajectory; UNIVERSE stats from the tuning-split cross-section — **DISTINCT** (this is what makes κ identifiable; final-review item b). Build `BaselineStats(self_stats, universe_stats)` per master.
- **SNR alignment (final-review item a):** decide align-vs-document for the σ=1 / 1.4826·MAD mismatch and record the δ→SNR map in the methods. (Currently documented in pre-reg; revisit if the paper needs δ=SNR.)
- **Add the self≠universe integration test (final-review item c)** before any deployment use.

### Phase 4 — Tuning-split calibration → Part-2 candidate
- Run `run_calibration` with the REAL tuning-split anchors/cov (κ now live) → grid-winner (bucket/M/τ/weights/κ). This is the candidate Part-2 tuple. Still reversible (tuning-split only, no locked test).

### Phase 5 — Non-trivial early baselines (B1/B2/B3)
- `baselines.py`: B1 leverage-percentile tripwire (fires at the master's own pre-T0 p90 leverage), B2 drawdown-velocity (first derivative of equity DD), B3 heuristic (leverage-up AND adding into a loser). All run under the IDENTICAL guard band + input windows as the detector (equal causal footing). B0 terminal-equity = "too-late" reference (lead-time ≈ 0).

### Phase 6 — Experiment harness (A / B / C) + stats
- **Claim A (lead-time):** per idiosyncratic blow-up master, lead-time = T(blow-up) − T(first guard-banded sustained alert); advantage over best(B1,B2,B3); event-clustered bootstrap CI by liquidation-DAY; leave-one-event-out. Gate: median advantage > 0, CI excludes 0.
- **Claim B (discrimination):** AUC (blows-up-within-Δ vs not), volatility-null FPR, PPV at operating point + cost curve; event-clustered CIs. Gates: AUC-CI lower > 0.65, FPR < 0.10, PPV ≥ 0.30.
- **Claim C (impact):** dimensionless sensitivity surface; no $ in abstract.
- **Ablation:** discipline-only retains ≥50% of full lead-time, event-clustered CI excludes 0 (the harness from Plan-2 `ablation.py`, now on real data).
- Run A/B/C/ablation on TUNING+VALIDATION first (exploratory, reversible) to sanity-check the harness end-to-end.

### Phase 7 — Pre-registration Part 2 LOCK  ⛔ HUMAN GATE
- Freeze the Part-2 tuple (detector + α + M + composite + guard-band + ablation bar + the tuning-split-calibrated winner) in a timestamped commit; publish its hash in the paper. **Sean approves this commit. Nothing past here runs unattended.**

### Phase 8 — Locked-test read + final results  ⛔ HUMAN GATE
- Read the SEALED locked-test split exactly once. Run A/B/C/ablation. Report the pre-registered gates pass/fail honestly. Robustness reruns (dd_pct ∈ {0.5,0.7,0.85}; T₀ fallback).

### Phase 9 — Paper assembly + arXiv
- Assemble per spec §8; reproducibility appendix (archived raw responses + commit hashes); Wynn-et-al case-study appendix (facts only, excluded from stats); LaTeX/figures; submit for Monday listing (Sun ~13:55 ET = Mon ~01:55 Taiwan).

---

## Automatable tonight (reversible) vs human-gated
- **Auto (tonight):** Phase 1 (scaled), Phase 2 split, Phase 3 baseline builder + tests, Phase 4 provisional calibration, Phase 5 baselines, Phase 6 on tuning+validation (exploratory). All reversible, no locked-test contact.
- **Human-gated (Sean):** Phase 7 lock, Phase 8 locked-test read, Phase 9 arXiv submission (account + Monday timing).

## Build constraints
Branch `copytrading-drift-demo`; detector frozen (no edits to `detector/` logic except the SNR-alignment decision + the self≠universe test); UTC; archive raw API responses; event-clustered stats only; sell lead-time/auditable/discrimination, never DD-reduction.
