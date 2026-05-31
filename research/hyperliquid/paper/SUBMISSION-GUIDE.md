# arXiv Submission Guide — Copy-Trading Drift Paper

> Status: **paper compiled (`main.pdf`, 189 KB), arXiv-ready.** Last human steps are yours
> (arXiv account + the irreversible submit). Everything else is done.

## What's in this folder
- `main.tex` — the paper (compiles clean with tectonic/pdflatex; `main.pdf` is the proof).
- `main.bbl` — compiled bibliography (include this so arXiv doesn't need to run BibTeX).
- `refs.bib` — bib source (for Overleaf / re-compile; NOT needed in the arXiv tarball).
- `figures/fig1_boundary.pdf` … `fig4_casestudy.pdf` — the 4 figures.
- `make_figures.py` + `figure_data.json` — reproducible figure pipeline.
- `arxiv-submission.tar.gz` — **the exact tarball to upload** (main.tex + main.bbl + 4 figure PDFs).

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
   - **Title**: The Limits of Behavioral Early Warning for Copy-Trading Blow-Ups: A High-Precision, Low-Recall Detector and the Blow-Ups It Cannot See
   - **Authors**: Syuan Wei Peng (Sean Peng), Mnemox AI
   - **Abstract**: paste the abstract from `main.tex` (the `\begin{abstract}` block).
   - **Comments**: e.g. "10 pages, 4 figures. Observational study on a scaled Hyperliquid cohort; data/code available."
7. **Timing for best listing position** (per `behavioral-drift-paper-arxiv-2026-05.md`): submit **Sunday ~13:55 ET = Monday ~01:55 Taiwan** to land at the top of Monday's q-fin.TR listing.
8. Submit. (This is the irreversible step — once announced, it's public.)

## ⚠️ Honesty checks before you press submit (don't skip — these protect you in review)
The paper is deliberately, prominently honest. Confirm you're OK publishing these as stated:
- It is **observational / exploratory on a SCALED cohort** (199 behavioral masters, 1206 labeled), **NOT** the full-universe pre-registered locked-test read. The paper says so three times.
- **Recall is low (~24%)** — useless for the ~76% of blow-ups that are sudden. Stated in abstract, §5.2, Discussion.
- The **gradual-leverage subclass is defined post hoc** (circularity), with the causal pre-registered fix named as future work.
- All numbers match the figures (reconciled): 22/93 (~24%) behavior-leads, 53% sudden, median lead ≈0, behavior-leads subset 9.6 d, 21/22 exposure-driven; detector FPR 0.048 / recall 0.238 / lead 27.9 d.

If you'd rather strengthen it to the full-universe pre-registered run BEFORE submitting (higher confidence, but ~12 h of fetching + the irreversible Part-2 lock), say so and I'll do that pass first. Otherwise this is a legitimate, submittable exploratory paper as-is.

## Reproducibility shipped with the paper
- Detector + harness: `research/hyperliquid/detector/`, `research/hyperliquid/experiments/` (204 tests).
- Cohort + fair comparison: `cohort_stage1.json`, `fair_comparison.py` + `fair_comparison_results.json`.
- Figures: `make_figures.py` + `figure_data.json`.
