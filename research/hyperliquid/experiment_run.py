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


def main(eval_split="testval", out_path=None, lock_cfg=None):
    # Lazy import avoids a module-level cycle (fair_comparison imports build_universe_stats).
    from research.hyperliquid.fair_comparison import choose_detector_cfg, _make_cfg

    d = json.loads(IN.read_text())
    ms = d["masters"]
    out_path = Path(out_path) if out_path else OUT
    tuning = [m for m in ms if m["split"] == "tuning"]
    if eval_split == "val":
        holdout = [m for m in ms if m["split"] == "val"]
    elif eval_split == "test":
        holdout = [m for m in ms if m["split"] == "test"]
    else:
        holdout = [m for m in ms if m["split"] in ("test", "val")]
    holdout_blow = [m for m in holdout if m["label"] == "blowup"]

    universe = build_universe_stats(tuning)
    tuning_blow = [m for m in tuning if m["label"] == "blowup"]
    tuning_stable = [m for m in tuning if m["label"] == "stable"]

    # SAME operating point as the fair comparison: chosen on TUNING only (no snooping),
    # or the EXACT frozen cfg for the locked-test read.
    if lock_cfg is not None:
        cfg = _make_cfg(lock_cfg[0], float(lock_cfg[1]))
        rederived, _, _ = choose_detector_cfg(tuning_blow, tuning_stable, universe)
        op_note = (f"LOCKED operating point M={lock_cfg[0]} kappa={lock_cfg[1]} "
                   f"(tuning re-derivation M={rederived.M} kappa={rederived.kappa}: "
                   f"{'MATCH' if (rederived.M, rederived.kappa) == (lock_cfg[0], float(lock_cfg[1])) else 'MISMATCH'})")
    else:
        cfg, _, sel = choose_detector_cfg(tuning_blow, tuning_stable, universe)
        op_note = f"operating point chosen on tuning: M={cfg.M} kappa={cfg.kappa} ({sel})"

    print(f"universe from {len(tuning)} tuning masters; eval split={eval_split} "
          f"holdout {len(holdout)} ({len(holdout_blow)} blowup)")
    print(op_note)

    A = claim_a(holdout_blow, universe, cfg)
    B = claim_b(holdout, universe, cfg)
    ABL = ablation(holdout_blow, universe, cfg)

    # ablation >=50% bar (controller-side check)
    abl_bar = None
    if ABL["lead_ratio"] is not None:
        abl_bar = (ABL["lead_ratio"] >= 0.50 and ABL["disc_ci_low"] > 0)

    results = {
        "full_universe": True,
        "eval_split": eval_split,
        "locked_test_read": lock_cfg is not None,
        "operating_point": {"M": cfg.M, "kappa": cfg.kappa, "tau": 0.3, "note": op_note},
        "n_tuning": len(tuning), "n_holdout": len(holdout), "n_holdout_blowup": len(holdout_blow),
        "claim_A": {k: A[k] for k in ("median_advantage", "ci_low", "ci_high", "n_masters", "n_events", "passed")},
        "claim_B": {k: B[k] for k in ("auc", "auc_ci_low", "auc_ci_high", "fpr", "ppv", "n_blowup", "n_stable", "confusion", "passed")},
        "ablation": {k: ABL[k] for k in ("full_median_lead", "disc_median_lead", "lead_ratio", "disc_ci_low", "disc_ci_high", "n_masters", "n_events")},
        "ablation_50pct_bar": abl_bar,
    }
    out_path.write_text(json.dumps(results, indent=2))

    print(f"\n=== eval split: {eval_split}  (locked-test read: {lock_cfg is not None}) -> {out_path.name} ===")
    print("=== CLAIM A (lead-time advantage over best baseline) ===")
    print(f"  median advantage: {A['median_advantage']:.1f}h | 95% CI [{A['ci_low']:.1f}, {A['ci_high']:.1f}] "
          f"| events={A['n_events']} | PASS={A['passed']}")
    print("=== CLAIM B (blowup vs stable discrimination) ===")
    print(f"  AUC={B['auc']:.3f} CI-low={B['auc_ci_low']:.3f} | FPR={B['fpr']:.3f} | PPV={B['ppv']:.3f} "
          f"| {B['confusion']} | PASS={B['passed']}")
    print("=== ABLATION (discipline-only vs full lead) ===")
    dm = ABL['disc_median_lead']
    print(f"  full_med={ABL['full_median_lead']:.1f}h disc_med={dm if dm is None else round(dm,1)}h "
          f"ratio={ABL['lead_ratio']} disc_CI_low={ABL['disc_ci_low']:.1f} | >=50%bar={abl_bar}")
    return results


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-split", choices=["val", "test", "testval"], default="testval")
    ap.add_argument("--out", default=None)
    ap.add_argument("--lock-cfg", default=None, help="frozen operating point 'M,kappa'")
    a = ap.parse_args()
    lc = None
    if a.lock_cfg:
        parts = a.lock_cfg.split(",")
        lc = (int(parts[0]), float(parts[1]))
    main(eval_split=a.eval_split, out_path=a.out, lock_cfg=lc)
