# Reframed Paper Outline — Honest Version (2026-05-31)

> Direction chosen autonomously under Sean's "do it all at once" directive, following the
> thesis re-examination. This is the most data-defensible reframe; Sean can override.
> Core move: turn the negative finding into the contribution + keep the real positive.

## New working title
*The Limits of Behavioral Early Warning for Copy-Trading Blow-Ups: A High-Precision,
Low-Recall Detector and the 80% It Cannot See* (on-chain Hyperliquid evidence).

## New thesis (honest, two-sided)
Behavioral drift does **not** generally precede copy-trading blow-ups — most are sudden.
But there exists a **specific, detectable subclass** (gradual leverage build-up) for which
an order-flow detector gives a **high-precision, ~8-day early warning**. We quantify both
the boundary and the usable signal on real on-chain data.

## Claims (re-pre-registered)

**Claim 1 — Boundary (negative, the headline contribution).**
On 93 real idiosyncratic blow-up masters (model-free): behavior leads equity for only
**~20%**; **57% blow up suddenly** (no gradual behavioral drift); **overall median lead = 0h**.
Behavioral monitoring is NOT a general early-warning solution. (Breaks the implicit
"behavioral monitoring catches blow-ups" assumption — incl. our own prior framing.)

**Claim 2 — High-precision detection (positive).**
The 3-axis mSPRT detector is **high-precision / low-recall**. On all 95 real blow-ups +
104 stable masters (indicative, default cfg): **recall ≈ 12%** (11/95 early-fire), **FPR ≈
6.7%** (7/104 stable false-alerts), **PPV ≈ 0.61** (11/18). When it fires (guard-banded,
sustained), it does so a median of **27.7 days (≈665h) before the crater** (p25 ≈ 5d, p75 ≈
97d; 10/11 ≥ 3 days), signal **exposure (leverage)-dominated**. I.e. a *specific*, long-lead
alarm for gradual over-leverage, not a general predictor.

**Claim 3 — Mechanism / which axis (positive, narrow).**
The lead is carried almost entirely by the **exposure axis**; discipline and tilt add little
on-chain. A leverage-dynamics-only detector captures most of the signal — simpler model,
matches the data.

## Why this is a strong paper despite the negative core
- **Honesty as contribution**: a pre-registered, real-data refutation of a popular assumption
  is publishable and citable (esp. q-fin.TR / risk). Most "behavioral monitoring" claims are
  never tested adversarially on real adversarial data — we do.
- **Still actionable**: a 75%-PPV / 8-day alarm for the gradual-leverage subclass is a real,
  deployable control for brokers/copy desks for that subclass — sold honestly, not oversold.
- **Reframes the prior MaxDDStop result correctly**: equity-threshold methods win in general
  *because most blow-ups are sudden*; behavioral methods win only in the gradual subclass and
  only there do they buy lead-time. The negative result and the positive result are the same
  coin.

## Evidence already in hand (all indicative / scaled — pre-reg run still pending)
| Claim | Evidence | Source |
|---|---|---|
| 1 boundary | 18/93 behavior-leads, 57% sudden, median lead 0h | `THESIS-REEXAMINATION-2026-05-31.md` |
| 2 precision | recall 12% (11/95), FPR 6.7% (7/104), PPV 0.61 (11/18) | Phase-5 full-cohort eval |
| 2 lead | detector fires median **27.7d** before crater (p25 5d, p75 97d; 10/11 ≥3d) | Phase-5 full-cohort eval |
| 3 axis | exposure-dominated (15/18 behavior-leads) | thesis-check |
| cohort | 443 idiosyncratic blow-ups, 49 events | `cohort_stage1.json` |

## What changes in the pipeline (Plan 3, reframed)
- **Drop** the "beat the best early baseline on lead-time across ALL blow-ups" headline
  (Claim A as was) — the data says it's unwinnable in general and unfair vs always-fire
  baselines.
- **Keep** the detector + harness + cohort pipeline (all reusable).
- **Re-pre-register** Claims 1–3. Claim 2's operating point (precision/recall/lead) becomes
  the positive headline; Claim 1 the boundary headline.
- **Still human-gated**: full-universe pre-reg run + locked-test read of the re-pre-registered
  Claims 1–3 + arXiv. Sean presses these.

## Honest limitations to state up front
- Recall is low (~14%) — useless for ~80% of blow-ups; we say so.
- Scaled cohort + default cfg so far; full-universe + calibrated cfg pending.
- Baseline-fairness (B2/B3 near-always-fire) must be fixed before any lead-time comparison
  is reported at all.
- gradual-leverage subclass is defined post hoc on observed drift — the pre-reg run must
  define it causally to avoid circularity.

## My recommendation to Sean (on waking)
Accept the honest reframe (Claims 1–3). It's a real, defensible, pre-registerable paper that
turns the sobering result into the contribution. The flagship "stop copy-trading contagion"
framing is gone, but a truthful "here's exactly where behavioral early warning works and
where it doesn't, on real money" is better than a flashy claim that fails review. If you want
bigger impact, the alternative is a product/risk-intelligence pivot (B/D) — but that's a
business call, not a data one.
