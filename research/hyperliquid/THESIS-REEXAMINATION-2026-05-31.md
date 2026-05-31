# Thesis Re-examination (2026-05-31)

> Triggered by the Phase-5 indicative negative result (detector loses to baselines).
> Method: a MODEL-FREE test of the thesis's load-bearing assumption on 93 real blowup masters.

## The load-bearing assumption

The paper's reframe rests on: **a master's observable behavioral drift LEADS the equity
damage, giving followers lead-time the equity itself cannot.** If behavior doesn't lead
equity, there is no lead-time to sell, regardless of detector quality.

## What the real data says (model-free, no detector)

For each blowup master: T_behavior = first clear degradation vs its own early-window
baseline (leverage↑ / loser-add / stop-rate↓); T_equity = first drop below 90% peak.

| Finding | Value |
|---|---|
| Blowups with ANY detectable gradual behavioral degradation | **40 / 93 (43%)** — 57% blow up with no gradual behavioral signal (sudden) |
| Of those 40, behavior LEADS equity (lead > 0) | **18 (45%)** |
| Equity leads behavior | 14 (35%) |
| Simultaneous | 8 |
| **Overall median lead** | **0h (behavior ≈ equity, not leading)** |
| Among the behavior-leads subset | median **200h (~8 days)**, almost all **exposure (leverage)** axis (15/18) |

## Honest interpretation

1. **The thesis holds for only ~20% of blowups** (18/93). For those, behavior genuinely
   leads by ~8 days, dominated by gradual leverage build-up.
2. **57% of blowups are "sudden"** — no gradual behavioral drift to detect at all (one big
   trade, a gap, or always-aggressive behavior with no "drift" baseline).
3. **Overall, behavior does NOT lead equity** (median lead 0). It's not a general law.
4. This explains the Phase-5 loss: the mSPRT detector assumes *gradual sustained* drift;
   most real blowups don't have it, so simple tripwires (and equity itself) fire as early
   or earlier.

## Reframe options

**A — Narrow the claim to the detectable subclass (honest, smaller).**
Paper becomes: "We identify and give ~8-day early warning for a specific, important blowup
subclass — *gradual leverage-drift* masters — on real on-chain data." Honestly report it's
useless for sudden blowups. Real value for that subclass; modest impact.

**B — Pivot the metric: fragility discrimination, not lead-time.**
Drop "predict when," ask "given a market shock, who was over-leveraged going in and dies vs
survives." But Phase-5 Claim B (AUC 0.586) was also weak — needs work, uncertain.

**C — Pivot the signal: leverage-only, drop the 3-axis story.**
The lead is almost entirely exposure/leverage; discipline+tilt barely contribute. A focused
"leverage-dynamics early warning" is simpler and matches the data — but still only the ~20%.

**D — Bigger pivot / accept the thesis is weak.**
If the core hook only covers 20% and behavior doesn't generally lead, the contribution may
be too thin for the flagship framing; consider a different angle entirely (e.g. a *risk-
intelligence* product story over a *prediction* paper, or a different dataset/problem).

**E — Redefine the event.** dd=70% may be too catastrophic/sudden; a dd=50% "serious
drawdown" might be more gradual and more behaviorally-detectable. Cheap to test, but risks
looking like fishing for a definition that works.

## My read

This is a hard hit but not a death sentence. The cleanest honest path is **A+C**: a focused,
modest paper on early warning for *gradual leverage-drift* blowups (the ~20% where behavior
truly leads), exposure-centric, with the sudden-blowup limitation reported up front. The
flagship "detect copy-trading blowups before they spread" framing is **not supported by the
data as a general claim** — it would need either the A+C narrowing or a real pivot (B/D).

**The no-data-snooping discipline is what surfaced this** before submission rather than after
rejection. Whatever the direction, the machinery (detector + harness + real cohort pipeline)
is reusable and the negative finding itself is publishable honesty.
