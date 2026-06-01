# arXiv Submission Guide — Copy-Trading Drift Paper

> Status: **paper compiled (`main.pdf`, 12 pages, ~174 KB), arXiv-ready.** This is the
> **full-universe, pre-registered** version (the operating point was frozen before the
> sealed test was read). Last human steps are yours: arXiv account + the irreversible submit.

## What's in this folder
- `main.tex` — the paper (compiles clean with tectonic/pdflatex; `main.pdf` is the proof).
- `main.bbl` — compiled bibliography (include this so arXiv doesn't need to run BibTeX).
- `refs.bib` — bib source; **included in the tarball** so it compiles cleanly on any system
  (arXiv / Overleaf / pdflatex+bibtex / tectonic), not only those that trust the prebuilt `.bbl`.
  Verified: the tarball compiles standalone to the same 12-page PDF with intact references.
- `figures/fig1_boundary.pdf`, `fig2_fpr_recall.pdf`, `fig3_leadtime.pdf` — the **3 figures**.
  (An earlier `fig4_casestudy.pdf` was dropped: the on-chain leverage proxy is too coarse
  to anchor a single-master case study responsibly. It is not referenced by the paper.)
- `make_figures.py` + `figure_data.json` — reproducible figure pipeline.
- `arxiv-submission.tar.gz` — **the exact tarball to upload** (main.tex + main.bbl + refs.bib + 3 figure PDFs).

## Preview before you submit (pick one)
- **Easiest**: open `main.pdf` in this folder (already compiled).
- **Overleaf**: New Project → Upload `main.tex` + `refs.bib` + `figures/` → Recompile.

## arXiv submission (your account; ~10 min)
1. Log in at arxiv.org → **Submit** → Start New Submission.
2. **License**: CC BY 4.0 (recommended for visibility) — or arXiv default if you prefer.
3. **Upload** `arxiv-submission.tar.gz`. arXiv will compile it; confirm the preview PDF matches `main.pdf`.
4. **Primary category**: `q-fin.TR` (Trading & Market Microstructure). **Cross-list** (optional): `q-fin.RM` (Risk Management).
5. **Endorsement**: q-fin.TR needs an endorser if your account isn't auto-endorsed — **Yijia Xiao (UCLA)** already agreed (2026-05-20). If prompted, request endorsement from them.
6. **Metadata** (copy from the paper):
   - **Title**: The Limits of Behavioral Early Warning for Copy-Trading Blow-Ups: A Pre-Registered, Full-Universe On-Chain Study (Hyperliquid)
   - **Authors**: Syuan Wei Peng (Sean Peng), Mnemox AI
   - **Abstract**: paste the abstract from `main.tex` (the `\begin{abstract}` block).
   - **Comments**: e.g. "12 pages, 3 figures. Pre-registered, full-universe observational study on Hyperliquid; operating point frozen before the sealed test was read once; data/code available."
7. **Timing for best listing position** (per `behavioral-drift-paper-arxiv-2026-05.md`): submit **Sunday ~13:55 ET = Monday ~01:55 Taiwan** to land at the top of Monday's q-fin.TR listing.
8. Submit. (This is the irreversible step — once announced, it's public.)

## ⚠️ Honesty checks before you press submit (don't skip — these protect you in review)
This version is a **clean strong-negative**. Confirm you're OK publishing these as stated:
- It is **pre-registered and full-universe**: 37,895 leaderboard addresses → 10,395 qualified
  (pre-T0 peak ≥ $25k, no survival filter), 2,621 idiosyncratic loss-confirmed blow-ups across
  48 crash-days, behavioral sub-cohort 3,455 (2,482 blow-up / 973 stable). The detector form,
  operating point (M=3, κ=7), and claim gates were **frozen in a timestamped commit before the
  sealed test (990 blow-up / 404 stable) was read once.**
- **The headline is negative**: behavioral drift leads equity for only **~9% (216 of 2,477)**;
  **69% of blow-ups are sudden**; the overall **median lead is −8 days** (behavior usually *lags*).
- **The pre-registered detector confirms the boundary by failing**: **chance-level discrimination
  (AUC 0.49, CI low 0.47) at 2% recall.** Its only virtue is the lowest FPR of any method
  (0.040, ~1.9× below the leverage tripwire) — worthless at 2% coverage.
- This **overturns the earlier scaled, exploratory version** of the project. That cohort was
  current-value-filtered and withdrawal-contaminated (at T0, ~65% of equity-only craters were
  withdrawals, not losses); the loss-confirmed labeling rule removes that artifact here.
- The residual signal is **exposure (gradual over-leveraging)** — 215 of 216 behavior-leads cases —
  but on a coarse on-chain proxy, so it's reported as a correlate, not a validated mechanism.

### Numbers, reconciled with the figures (all from the sealed-test / full-universe run)
- Boundary (Fig 1): 216/2,477 ≈ 9% behavior-leads; 1,706/2,477 ≈ 69% sudden; median lead −8 d;
  positive-lead subset (Fig 3) median ≈13 d (IQR 7.3–24.5 d); 215/216 exposure-driven.
- Fair comparison (Table 1 / Fig 2): Detector FPR **0.040** (16/404) / recall **0.021** (21/990) /
  median lead 49 d / AUC **0.49**; B1 0.074 / 0.105 / 52 d; B2 0.225 / 0.227 / 70 d; B3 0.171 / 0.153 / 72 d.
- Pre-registered claim gates both **FAIL** (as expected for a negative result): Claim A
  advantage 0; Claim B AUC 0.49 (CI low 0.47), PPV 0.57.

## Reproducibility shipped with the paper
- Detector + harness: `research/hyperliquid/detector/`, `research/hyperliquid/experiments/`.
- Pipeline: `stage1_full_universe.py`, `cohort_behavioral_fetch_full.py`, `fair_comparison.py`
  (+ `--eval-split` / `--lock-cfg` no-snoop firewall), `experiment_run.py`.
- Results: `fair_comparison_results.json`, `plan3_experiment_results.json` (`locked_test_read: true`).
- Pre-registration: `PRE-REGISTRATION-DRAFT.md` (Part 2 locked in the timestamped commit).
- Figures: `make_figures.py` + `figure_data.json`.
