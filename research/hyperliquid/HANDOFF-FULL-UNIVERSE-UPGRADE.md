# HANDOFF — Full-Universe Upgrade + arXiv Submission (copy-trading drift paper)

> For a FRESH session. Self-contained. Branch `copytrading-drift-demo`, repo
> `C:/Users/johns/projects/tradememory-protocol`. Read this top-to-bottom first.

## The task (one line)
Upgrade the copy-trading drift paper from the **exploratory/scaled** run (199 masters)
to the **full-universe pre-registered** run, refresh every number + figure + the LaTeX,
re-compile, and leave it arXiv-ready. Sean submits tomorrow (his account, his press).

## Where things stand (DONE, exploratory version)
- Paper is fully written + compiles: `research/hyperliquid/paper/main.tex` → `main.pdf`
  (tectonic), 4 figures, 18 refs, `arxiv-submission.tar.gz`, `SUBMISSION-GUIDE.md`.
- Honest reframe (q-fin.TR): *"The Limits of Behavioral Early Warning for Copy-Trading
  Blow-Ups: A High-Precision, Low-Recall Detector and the Blow-Ups It Cannot See."*
- Detector machinery: `research/hyperliquid/detector/` (204 tests green:
  `python -m pytest research/hyperliquid/tests/ -q`). Experiment harness:
  `research/hyperliquid/experiments/`. All reusable as-is.
- Current headline numbers (SCALED, to be REPLACED by full-universe):
  boundary 22/93 (~24%) behavior-leads, 53% sudden, median lead ~0, subset 9.6d,
  21/22 exposure; fair held-out detector FPR 0.048 / recall 0.238 / lead 27.9d vs
  B1/B2/B3. HEAD `1b21f85`.

## Why upgrade
Sean wants his first paper as strong as possible: the full-universe, pre-registered,
locked-test run instead of the scaled/indicative one. Time is fine (submit tomorrow);
run it under `/goal` so it pushes through without stopping for minor decisions.

## The upgrade steps (in order)

### 1. Full-universe Stage-1 labeling (~4h fetch)
- Pre-reg universe = **pre-T0 peak account value ≥ \$25k**, T0 = 2025-06-01 UTC, window
  end 2026-04-30. **Do NOT pre-filter on current accountValue** — blow-up masters now
  sit below \$25k; filtering on current value drops exactly the events you need. Fetch
  `portfolio` for the FULL leaderboard (37,879 addrs from
  `stats-data.hyperliquid.xyz/Mainnet/leaderboard`), compute each one's pre-T0 peak from
  `accountValueHistory`, keep peak ≥ \$25k, then label via the forward-only rule.
- Reuse `research/hyperliquid/stage1_label.py` (robust 429-retry, equity-only labeling)
  — generalize its `universe_addrs.txt` input to the full leaderboard (write all 37,879
  addrs, or stream the leaderboard directly). Run in background. Output: a full
  `cohort_stage1.json` with base rate, idiosyncratic count, effective-N (independent
  crash-days), market-event-day tagging (τ=3%).

### 2. Full behavioral Stage-2 fetch
- `research/hyperliquid/cohort_behavioral_fetch.py` — raise/remove the `CAP_BLOWUP=120 /
  CAP_STABLE=120` caps so ALL idiosyncratic blow-ups + a seed-fixed matched stable sample
  are fetched (fills/orders/ledger → per-bucket primitives). Background; hours.

### 3. Re-run experiments on the full cohort
- `fair_comparison.py` (operating point chosen on TUNING, reported on held-out — no test
  snooping) → refreshed FPR/recall/lead table. `experiment_run.py` → Claim A/B/ablation.
  The model-free boundary check (in `make_figures.py`'s `compute_model_free_lead`) → the
  53%/24%/9.6d/exposure-share numbers, now on the full blow-up panel.

### 4. ⛔ Pre-registration Part 2 lock + locked-test read (IRREVERSIBLE — confirm with Sean)
- Freeze the detector + operating-point-selection rule + all numeric targets in a
  timestamped commit (pre-reg Part 2), THEN read the sealed locked-test split once for the
  final Claim A/B numbers. This is the one irreversible scientific step. **Even under
  /goal, surface a one-line confirmation to Sean before the lock commit** (it defines the
  pre-registration; he asked to keep this human-gated historically). See
  `research/hyperliquid/PRE-REGISTRATION-DRAFT.md` (Part 1 locked `92e343c`; Part 2 +
  decisions checklist already drafted, incl. the early-window-baseline decision).

### 5. Refresh the paper
- Update every number in `paper/main.tex` to the full-universe results (boundary, fair
  table, lead, exposure share, cohort sizes). Regenerate figures: `make_figures.py`
  (reads the full cohort) → 4 PDFs + `figure_data.json`. **Keep text↔figure numbers
  identical** (a prior bug: they diverged; reconcile carefully).
- If the lock + locked-test were done, change the epistemic framing from
  "exploratory/scaled/indicative" to "pre-registered full-universe" in abstract, intro,
  §5, discussion — but KEEP the honest two-sided message (behavior doesn't generally lead;
  high-precision niche; low recall stated). Don't oversell.

### 6. Re-compile + repackage
- Compile with tectonic. **tectonic on this Windows box needs a fontconfig shim**: write a
  minimal `fonts.conf` (`<dir>C:/Windows/Fonts</dir>` + a cachedir + empty `<config/>`),
  set `FONTCONFIG_FILE` to it, then `tectonic --keep-intermediates main.tex`. That produced
  `main.pdf` + `main.bbl` cleanly. Rebuild `arxiv-submission.tar.gz` (main.tex + main.bbl +
  figures/*.pdf). Update `SUBMISSION-GUIDE.md` if numbers in it changed.

### 7. Hand back to Sean
- He previews `main.pdf`, runs the honesty checks in `SUBMISSION-GUIDE.md`, uploads
  `arxiv-submission.tar.gz` to arXiv (q-fin.TR primary, q-fin.RM cross-list, Yijia Xiao
  endorsement), Monday-listing timing (Sun ~13:55 ET = Mon ~01:55 Taiwan). That submit is
  his and irreversible.

## Hard constraints
- Branch `copytrading-drift-demo`. UTC everywhere. Commit + push each step; update CLAUDE.md
  Recent Changes after each (Sean's rule). Don't touch `src/tradememory/mcp_server.py` or
  unrelated `M`/`??` files in the tree (they're other work).
- **No data snooping**: operating point / any tuning on the tuning split ONLY; the locked
  test is read exactly once, after the Part-2 lock commit.
- Real-data gotchas already solved — keep them: sparse count/rate primitives use a
  **std-based scale, not MAD** (`_scale` in `stage2_behavioral.py`/`experiment_run.py`);
  `historicalOrders` are **nested under "order"** (`normalize.order_events` handles both);
  the **early-window self-baseline** (healthy_frac 0.80, min_healthy 5, fall-back-not-
  exclude) is Sean's chosen baseline method (`experiments/early_baseline.py`); the
  **10k-fill cap** means high-freq masters have no pre-T0 fills → that's WHY baseline is
  early-window not pre-T0.

## Key files
- Paper: `research/hyperliquid/paper/` (main.tex, refs.bib, make_figures.py, figure_data.json,
  SUBMISSION-GUIDE.md, main.pdf, arxiv-submission.tar.gz).
- Pipeline drivers: `stage1_label.py`, `cohort_behavioral_fetch.py`, `fair_comparison.py`,
  `experiment_run.py` (all in `research/hyperliquid/`).
- Result/context docs: `THESIS-REEXAMINATION-2026-05-31.md`, `PHASE5-INDICATIVE-RESULTS.md`,
  `REFRAMED-PAPER-OUTLINE-2026-05-31.md`, `fair_comparison_results.json`,
  `PRE-REGISTRATION-DRAFT.md`.
- Detector + experiments packages + tests under `research/hyperliquid/{detector,experiments,tests}/`.

## Definition of done
Full-universe cohort fetched + labeled; experiments re-run (operating point on tuning,
locked-test read once after the Part-2 lock Sean confirmed); paper numbers + figures all
refreshed and text↔figure-consistent; `main.pdf` recompiles clean; `arxiv-submission.tar.gz`
rebuilt; CLAUDE.md updated; everything committed + pushed. Then ping Sean to preview +
submit.
