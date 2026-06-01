# Reframe proposal — full-universe result (for Sean's framing decision)

> **STATUS: PROPOSAL ONLY. Nothing locked, test sealed, main.tex untouched.** This is a
> concrete draft of what the reframed paper would look like, so the framing decision is
> made against real text, not abstractly. Numbers below are VAL + model-free boundary
> (indicative); the final headline numbers come from the locked-test read AFTER the
> Part-2 lock (the pattern is firm — val n=656, boundary n=2477 — test will only confirm).

## The decision in one line
The scaled paper's "usable high-precision detector" was an artifact of a
current-value-filtered, withdrawal-contaminated cohort. The clean full-universe
genuine-loss cohort gives a **stronger, cleaner NEGATIVE** and a detector that does not
work as a general discriminator. Recommended: **make the negative the paper** (Option A).

## Numbers (scaled → full-universe)
| metric | scaled (current paper) | full-universe (this run) |
|---|---|---|
| blow-up panel (≥20 buckets) | 93 | **2,477** |
| sudden (no gradual behavioral signal) | 53% | **69%** |
| behavior leads equity (of all) | 24% (22/93) | **9% (216/2,477)** |
| overall median lead | ~0 d | **−8 d** (behavior lags) |
| behavior-leads subset median lead | 9.6 d | 13.2 d (IQR 7.3–24.5) |
| exposure-driven among leads | 95.5% | **99.5%** |
| detector recall (held-out) | 0.238 | **0.030** |
| detector FPR (held-out) | 0.048 | 0.026 (still lowest) |
| Claim B AUC (CI-low) | ~0.59 | **0.499 (≈ chance)** |
| Claim A lead advantage vs baselines | fail | fail (0.0 h) |

## Proposed TITLE (was: "...A High-Precision, Low-Recall Detector and the Blow-Ups It Cannot See")
- **Primary:** *Behavioral Early Warning Does Not Generally Precede Copy-Trading
  Blow-Ups: Full-Universe On-Chain Evidence from Hyperliquid*
- **Alt (keeps "Limits" framing):** *The Limits of Behavioral Early Warning for
  Copy-Trading Blow-Ups: Most Are Sudden — A Pre-Registered Full-Universe On-Chain Study*

## Proposed ABSTRACT (draft, full-universe, honest)
> A common, rarely-tested assumption behind copy-trading risk controls is that
> "behavioral monitoring catches blow-ups" — that a master trader's conduct drifts
> *before* the equity damage that wipes out followers. We test this on the **full**
> public Hyperliquid perpetual-futures universe (37,895 leaderboard addresses; a
> pre-registered, frozen-at-T₀ cohort of 2,621 genuine loss-driven idiosyncratic
> blow-ups across 48 independent crash-days, labeled by a forward-only, withdrawal-
> filtered rule). On a model-free panel of 2,477 blow-up masters, behavioral drift
> leads equity for only **9%**; **69% blow up with no gradual behavioral signal at
> all**, and the overall median lead is **negative** — behavior, when it moves, usually
> lags the equity. A purpose-built three-axis mixture-SPRT detector, with its operating
> point fixed on a disjoint tuning split, confirms the boundary rather than beating it:
> it attains the lowest false-positive rate of any method (0.0XX) but a recall of only
> **0.0XX** and **chance-level discrimination** (AUC ≈ 0.50) on the locked test set. The
> one behavioral signal that survives is gradual leverage build-up (99.5% of the
> leading cases), and it precedes fewer than one in ten blow-ups. We conclude that
> behavioral early warning is **not** a viable general safety net for copy-trading
> blow-ups: most are sudden, an equity/drawdown stop dominates, and behavioral
> monitoring adds value only in a narrow gradual-leverage niche it cannot enlarge.
> *(0.0XX = filled from the locked-test read after Part-2 lock.)*

## Structural changes to main.tex (Stage 5, after lock)
1. **§Results Claim 1 (boundary) becomes THE headline** — 69%/9%/−8d, n=2,477. Strong.
2. **§Results Claim 2 (detector) is demoted to "confirms the boundary"** — lowest FPR but
   3% recall + AUC≈chance; the "high-precision niche" is honestly tiny (<10% of blow-ups).
   Keep the lowest-FPR + leverage-axis observations as the only-thing-that-survives note.
3. **Abstract / intro / discussion / conclusion**: exploratory/scaled → **pre-registered
   full-universe locked-test**; flip the "usable detector" positive to "the boundary is
   the result; the detector is its corollary." Keep withdrawal-filter + Option-B labeling
   in Data/Appendix (it's why the cohort is clean).
4. **Figures**: fig1 boundary + fig3 lead-time regenerate on full cohort (model-free,
   ready now). fig2 FPR/recall + fig4 case study regenerate after the locked-test read.
   `make_figures.py` is already data-driven so text↔figure stays consistent.
5. **Honesty checks**: low recall is now ~3% (state it); the post-hoc subclass caveat
   stays; add that the result REVERSES our earlier scaled framing (intellectual honesty).

## Option B (if you'd rather keep it two-sided)
Same numbers; keep a short detector subsection as a *narrow positive* ("a precise,
weeks-early flag for the ~3% gradual-leverage subset; FPR 2.6%, PPV 74%") instead of
demoting it. The title would keep a detector clause. I think A is stronger and more
defensible, but B is honest too.

## Product (TradeMemory / Edison) note — separate from the paper
The detector-as-general-broker-drift-API value prop is weakened. The honest pitch
becomes: *not* "we catch blow-ups," but (a) a precise niche flag for gradual-leverage
masters + (b) a rigorously-mapped boundary (most blow-ups are sudden → a broker still
needs an equity stop). That honesty could differentiate vs ZuluGuard's black-box
overclaim — but you should know this floor before the next Edison conversation.
See [[otso-edison-conversation-state]] [[tradememory-crypto-drift-pivot-2026-05-28]].

## After you decide
Pick A or B (+ a title) → I run `choose_detector_cfg` on tuning, show you the exact
(M, κ) + targets → **you say "lock"** → I commit pre-reg Part 2 (timestamped, irreversible)
→ read the locked test once → refresh numbers + 4 figures (text↔figure consistent) →
tectonic recompile → repackage `arxiv-submission.tar.gz` → ping you to preview. You submit.
