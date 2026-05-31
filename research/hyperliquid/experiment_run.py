"""Plan 3 Phase-5 INDICATIVE experiment run (SCALED / PROVISIONAL — NOT the pre-reg locked-test read).

Builds the cross-sectional universe distribution from the TUNING split's early-window
behavior, then runs Claim A (lead-time vs best baseline), Claim B (blowup-vs-stable
discrimination), and the discipline-only ablation on the held-out masters.

CAVEAT: scaled ~200-master cohort, a DEFAULT detector cfg (NOT the calibration winner),
exploratory split usage. This is the indicative "does it work end-to-end on real data"
result, NOT the pre-registered locked-test read (that runs on the full-universe cohort
after the Part-2 lock — human-gated).
"""
from __future__ import annotations

import json
from pathlib import Path

from research.hyperliquid.detector.config import AXES, PRIMITIVES, DetectorConfig, PrimitiveStats
from research.hyperliquid.experiments.experiment import claim_a, claim_b, ablation

IN = Path("research/hyperliquid/cohort_behavioral.json")
OUT = Path("research/hyperliquid/plan3_experiment_results.json")
EARLY_FRAC = 0.20


def _med(xs):
    return sorted(xs)[len(xs) // 2] if xs else 0.0


def _scale(xs):
    if len(xs) < 2:
        return 1.0
    mu = sum(xs) / len(xs)
    std = (sum((x - mu) ** 2 for x in xs) / len(xs)) ** 0.5
    return max(std, 0.05 * (1 + abs(_med(xs))), 1e-3)


def build_universe_stats(tuning_masters):
    """Cross-sectional universe distribution from tuning masters' early-window buckets."""
    pooled = {p: [] for a in AXES for p in PRIMITIVES[a]}
    for m in tuning_masters:
        s = m["series"]
        early = s[:max(1, int(len(s) * EARLY_FRAC))]
        for b in early:
            for p in pooled:
                pooled[p].append(b["prim"][p])
    return {a: {p: PrimitiveStats(_med(pooled[p]), _scale(pooled[p]), len(pooled[p]))
                for p in PRIMITIVES[a]} for a in AXES}


def main():
    d = json.loads(IN.read_text())
    ms = d["masters"]
    tuning = [m for m in ms if m["split"] == "tuning"]
    holdout = [m for m in ms if m["split"] in ("test", "val")]
    holdout_blow = [m for m in holdout if m["label"] == "blowup"]

    universe = build_universe_stats(tuning)
    cfg = DetectorConfig(
        bucket_ms=4 * 3600 * 1000, M=3,
        tau={a: 0.3 for a in AXES},
        weights={a: {p: 1 / 3 for p in PRIMITIVES[a]} for a in AXES},
        kappa=14, burn_in=20,
    )

    print(f"universe from {len(tuning)} tuning masters; "
          f"holdout {len(holdout)} ({len(holdout_blow)} blowup)")

    A = claim_a(holdout_blow, universe, cfg)
    B = claim_b(holdout, universe, cfg)
    ABL = ablation(holdout_blow, universe, cfg)

    # ablation >=50% bar (controller-side check)
    abl_bar = None
    if ABL["lead_ratio"] is not None:
        abl_bar = (ABL["lead_ratio"] >= 0.50 and ABL["disc_ci_low"] > 0)

    results = {
        "scaled_provisional": True,
        "note": "INDICATIVE — scaled cohort + default cfg, NOT the pre-reg locked-test read",
        "n_tuning": len(tuning), "n_holdout": len(holdout), "n_holdout_blowup": len(holdout_blow),
        "claim_A": {k: A[k] for k in ("median_advantage", "ci_low", "ci_high", "n_masters", "n_events", "passed")},
        "claim_B": {k: B[k] for k in ("auc", "auc_ci_low", "auc_ci_high", "fpr", "ppv", "n_blowup", "n_stable", "confusion", "passed")},
        "ablation": {k: ABL[k] for k in ("full_median_lead", "disc_median_lead", "lead_ratio", "disc_ci_low", "disc_ci_high", "n_masters", "n_events")},
        "ablation_50pct_bar": abl_bar,
    }
    OUT.write_text(json.dumps(results, indent=2))

    print("\n=== CLAIM A (lead-time advantage over best baseline) ===")
    print(f"  median advantage: {A['median_advantage']:.1f}h | 95% CI [{A['ci_low']:.1f}, {A['ci_high']:.1f}] "
          f"| events={A['n_events']} | PASS={A['passed']}")
    print("=== CLAIM B (blowup vs stable discrimination) ===")
    print(f"  AUC={B['auc']:.3f} CI-low={B['auc_ci_low']:.3f} | FPR={B['fpr']:.3f} | PPV={B['ppv']:.3f} "
          f"| {B['confusion']} | PASS={B['passed']}")
    print("=== ABLATION (discipline-only vs full lead) ===")
    print(f"  full_med={ABL['full_median_lead']:.1f}h disc_med={ABL['disc_median_lead']:.1f}h "
          f"ratio={ABL['lead_ratio']} disc_CI_low={ABL['disc_ci_low']:.1f} | >=50%bar={abl_bar}")


if __name__ == "__main__":
    main()
