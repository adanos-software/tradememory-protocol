"""Transparent FPR / recall / lead comparison — detector vs B1/B2/B3 on real data.

This is the FAIR re-run of the Plan-3 Phase-5 experiment. The Phase-5 indicative
result was unfair in three ways, all fixed here:

  1. the stability guard excluded ~40% of blowups (fixed in early_baseline.py:
     relaxed guard now falls back instead of excluding; this module simply uses
     the relaxed builder via experiment._eval_detector);
  2. B2/B3 "lead" looked huge only because those baselines fire on ~everything
     (a method that alerts on every master trivially "leads" the blowup) — so a
     raw lead-time comparison is meaningless;
  3. the detector ran on an arbitrary default cfg.

The fix is to stop reporting a single lead-time number and instead report, for
EVERY method side by side, the honest triple:

    FPR     — fraction of STABLE masters that raise a guard-banded alert
    recall  — fraction of BLOWUP masters that raise a guard-banded EARLY alert
              (an alert with positive lead before the blowup)
    lead    — median lead-time (hours / days) over the blowups where it fires
              with positive lead

A method that "leads" only because its FPR is ~1.0 is not winning; surfacing FPR
next to lead is the whole point.

Operating-point selection (NO test snooping)
--------------------------------------------
The detector's cfg is chosen on the TUNING split ONLY: grid M in {2,3,4} x kappa
in {7,14} (tau=0.3, equal weights, bucket=4h, burn_in=20). Pick the cfg whose
tuning-STABLE FPR <= 0.10 with the highest tuning-BLOWUP recall (tie-break:
longest median lead). If none clears FPR<=0.10, pick the lowest-FPR cfg. The
chosen cfg is then evaluated, untouched, on the held-out test+val masters. The
baselines B1/B2/B3 have no tunable operating point here (B3 is binary; B1/B2 use
their own fixed early-window p90 rule) — we report their NATURAL FPR/recall/lead.
That asymmetry is itself transparent: the detector pays an FPR budget; the
baselines spend whatever FPR their fixed rule happens to cost.

Imports: stdlib + research.hyperliquid.* only. No numpy, no tradememory.owm.*.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.hyperliquid.detector.config import AXES, PRIMITIVES, DetectorConfig
from research.hyperliquid.experiments.experiment import (
    _eval_detector,
    lead_time_hours,
)
from research.hyperliquid.experiments.baselines import (
    b1_leverage_percentile,
    b2_drawdown_velocity,
    b3_leverage_up_and_add,
)
from research.hyperliquid.experiment_run import build_universe_stats

IN = Path("research/hyperliquid/cohort_behavioral.json")
OUT = Path("research/hyperliquid/fair_comparison_results.json")

_HOURS_PER_DAY = 24.0
_BASELINE_GUARD_X = 0.70  # matches the detector default guard_x

# Detector operating-point grid (tuning-only).
_GRID_M = (2, 3, 4)
_GRID_KAPPA = (7.0, 14.0)
_BUCKET_MS = 4 * 3600 * 1000
_BURN_IN = 20
_TAU = 0.3
_FPR_BUDGET = 0.10


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _make_cfg(M: int, kappa: float) -> DetectorConfig:
    """Detector cfg for a grid point: tau=0.3 all axes, equal weights, bucket=4h."""
    return DetectorConfig(
        bucket_ms=_BUCKET_MS,
        M=M,
        tau={a: _TAU for a in AXES},
        weights={a: {p: 1.0 / len(PRIMITIVES[a]) for p in PRIMITIVES[a]} for a in AXES},
        kappa=kappa,
        burn_in=_BURN_IN,
    )


# ---------------------------------------------------------------------------
# per-method evaluation on a master set
# ---------------------------------------------------------------------------
def _detector_fires(master: dict, universe_stats: dict, cfg) -> tuple[bool, float | None]:
    """(fired_early, lead_hours) for the detector on one master.

    fired_early = the detector raised a guard-banded early alert (first_early_ms
    not None). lead_hours = forward lead from that alert to blowup_time, or None
    (no alert, or non-positive lead, or no blowup_time). For a STABLE master
    (blowup_time None) lead is always None, but fired_early can be True — that is
    exactly a false positive.
    """
    det = _eval_detector(master, universe_stats, cfg)
    alert_ms = det["first_early_ms"]
    fired = alert_ms is not None
    lead = lead_time_hours(master.get("blowup_time"), alert_ms)
    return fired, lead


def _baseline_fires(fn, master: dict) -> tuple[bool, float | None]:
    """(fired, lead_hours) for one B1/B2/B3 baseline on one master.

    fired = the baseline's guard-banded rule tripped (returned a bucket end_ms).
    lead = forward lead to blowup_time, or None.
    """
    alert_ms = fn(master["series"], master.get("first_liq_ms"), _BASELINE_GUARD_X)
    fired = alert_ms is not None
    lead = lead_time_hours(master.get("blowup_time"), alert_ms)
    return fired, lead


def _evaluate_method(
    fire_fn,
    blowups: list[dict],
    stables: list[dict],
) -> dict:
    """Compute FPR / recall / median-lead for a single method.

    fire_fn(master) -> (fired: bool, lead_hours: float | None).

    FPR    = fraction of STABLE masters with fired == True.
    recall = fraction of BLOWUP masters with fired == True AND lead > 0
             (a guard-banded EARLY alert: it fired before the blowup).
    lead   = median over the positive-lead blowups (the ones counted in recall).
    """
    # stable: false-positive rate
    fp = sum(1 for m in stables if fire_fn(m)[0])
    n_stable = len(stables)
    fpr = (fp / n_stable) if n_stable else 0.0

    # blowup: early-alert recall + leads
    early_hits = 0
    leads: list[float] = []
    for m in blowups:
        fired, lead = fire_fn(m)
        if fired and lead is not None and lead > 0:
            early_hits += 1
            leads.append(lead)
    n_blow = len(blowups)
    recall = (early_hits / n_blow) if n_blow else 0.0

    med_lead_h = _median(leads)
    med_lead_d = (med_lead_h / _HOURS_PER_DAY) if med_lead_h is not None else None

    return {
        "fpr": fpr,
        "recall": recall,
        "n_fire_blowup_early": early_hits,
        "median_lead_hours": med_lead_h,
        "median_lead_days": med_lead_d,
        "n_blowup": n_blow,
        "n_stable": n_stable,
        "fp": fp,
    }


# ---------------------------------------------------------------------------
# detector operating-point selection on the TUNING split
# ---------------------------------------------------------------------------
def choose_detector_cfg(tuning_blow: list[dict], tuning_stable: list[dict],
                        universe_stats: dict) -> tuple[DetectorConfig, list[dict], str]:
    """Grid the detector on TUNING and pick the operating cfg.

    Rule: among cfgs with tuning-stable FPR <= 0.10, take the highest tuning-blowup
    recall; tie-break on the longest median tuning lead. If none clears the FPR
    budget, take the lowest-FPR cfg (then highest recall, then longest lead).

    Returns (winner_cfg, grid_rows) where grid_rows logs every grid point's
    (M, kappa, fpr, recall, median_lead_hours) for transparency.
    """
    grid_rows: list[dict] = []
    for M in _GRID_M:
        for kappa in _GRID_KAPPA:
            cfg = _make_cfg(M, kappa)
            res = _evaluate_method(
                lambda m, c=cfg: _detector_fires(m, universe_stats, c),
                tuning_blow, tuning_stable,
            )
            grid_rows.append({
                "M": M,
                "kappa": kappa,
                "fpr": res["fpr"],
                "recall": res["recall"],
                "median_lead_hours": res["median_lead_hours"],
            })

    def lead_key(row):
        # None lead sorts lowest
        return row["median_lead_hours"] if row["median_lead_hours"] is not None else -1.0

    within_budget = [r for r in grid_rows if r["fpr"] <= _FPR_BUDGET]
    if within_budget:
        # highest recall, then longest median lead
        winner_row = max(within_budget, key=lambda r: (r["recall"], lead_key(r)))
        selection_note = (
            f"chose highest-recall cfg among the {len(within_budget)} grid points "
            f"with tuning-stable FPR <= {_FPR_BUDGET} (tie-break: longest tuning lead)"
        )
    else:
        # nothing clears the budget: lowest FPR, then highest recall, then longest lead
        winner_row = min(grid_rows, key=lambda r: (r["fpr"], -r["recall"], -lead_key(r)))
        selection_note = (
            f"NO grid point met tuning-stable FPR <= {_FPR_BUDGET}; fell back to the "
            f"lowest-FPR cfg (then highest recall, then longest lead)"
        )

    winner_cfg = _make_cfg(winner_row["M"], winner_row["kappa"])
    for r in grid_rows:
        r["selected"] = (r["M"] == winner_row["M"] and r["kappa"] == winner_row["kappa"])
    return winner_cfg, grid_rows, selection_note


# ---------------------------------------------------------------------------
# exclusion / fallback accounting on the held-out set (for the report)
# ---------------------------------------------------------------------------
def _baseline_accounting(blowups: list[dict], universe_stats: dict, cfg) -> dict:
    """How many held-out blowups are excluded vs use the fallback window now."""
    from research.hyperliquid.experiments.early_baseline import build_early_window_baseline
    excluded = fallback = normal = 0
    for m in blowups:
        _, info = build_early_window_baseline(
            m["series"], universe_stats, cfg, max_early_frac=0.20,
        )
        if info["excluded"]:
            excluded += 1
        elif info.get("fallback"):
            fallback += 1
        else:
            normal += 1
    n = len(blowups)
    return {
        "n_blowup": n,
        "excluded": excluded,
        "fallback": fallback,
        "normal": normal,
        "excluded_frac": (excluded / n) if n else 0.0,
        "fallback_frac": (fallback / n) if n else 0.0,
    }


# ---------------------------------------------------------------------------
# table rendering
# ---------------------------------------------------------------------------
def _fmt_lead(res: dict) -> str:
    h = res["median_lead_hours"]
    d = res["median_lead_days"]
    if h is None:
        return "      n/a"
    return f"{d:7.1f}d"


def render_table(rows: list[tuple[str, dict]]) -> str:
    """rows = [(method_name, eval_result), ...]."""
    lines = []
    header = f"{'method':<16} {'FPR':>7} {'recall':>8} {'med-lead':>10} {'fires(blowup-early)':>20}"
    lines.append(header)
    lines.append("-" * len(header))
    for name, res in rows:
        lines.append(
            f"{name:<16} {res['fpr']:>7.3f} {res['recall']:>8.3f} "
            f"{_fmt_lead(res):>10} "
            f"{res['n_fire_blowup_early']:>3}/{res['n_blowup']:<3} (n_stable={res['n_stable']})"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(eval_split="testval", out_path=None, lock_cfg=None) -> dict:
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

    tuning_blow = [m for m in tuning if m["label"] == "blowup"]
    tuning_stable = [m for m in tuning if m["label"] == "stable"]
    hold_blow = [m for m in holdout if m["label"] == "blowup"]
    hold_stable = [m for m in holdout if m["label"] == "stable"]

    universe = build_universe_stats(tuning)

    # ---- choose detector operating point on TUNING only -------------------
    cfg, grid_rows, selection_note = choose_detector_cfg(
        tuning_blow, tuning_stable, universe
    )
    if lock_cfg is not None:
        # Locked-test read: use the EXACT frozen operating point. Re-derive on tuning
        # and record whether it matches (the firewall guarantee: the locked cfg was
        # chosen with no test contact; the re-derivation MUST match it).
        rederived = (cfg.M, cfg.kappa)
        cfg = _make_cfg(lock_cfg[0], float(lock_cfg[1]))
        match = (rederived == (lock_cfg[0], float(lock_cfg[1])))
        selection_note += (f" | LOCKED cfg M={lock_cfg[0]} kappa={lock_cfg[1]} "
                           f"(tuning re-derivation M={rederived[0]} kappa={rederived[1]}: "
                           f"{'MATCH' if match else 'MISMATCH'})")
    chosen = {
        "M": cfg.M,
        "kappa": cfg.kappa,
        "tau": _TAU,
        "bucket_ms": cfg.bucket_ms,
        "burn_in": cfg.burn_in,
        "weights": "equal",
    }

    # ---- evaluate every method on the HELD-OUT test+val set ---------------
    det_res = _evaluate_method(
        lambda m: _detector_fires(m, universe, cfg), hold_blow, hold_stable
    )
    b1_res = _evaluate_method(
        lambda m: _baseline_fires(b1_leverage_percentile, m), hold_blow, hold_stable
    )
    b2_res = _evaluate_method(
        lambda m: _baseline_fires(b2_drawdown_velocity, m), hold_blow, hold_stable
    )
    b3_res = _evaluate_method(
        lambda m: _baseline_fires(b3_leverage_up_and_add, m), hold_blow, hold_stable
    )

    rows = [
        ("detector", det_res),
        ("B1 lev-p90", b1_res),
        ("B2 dd-velocity", b2_res),
        ("B3 lev-up+add", b3_res),
    ]
    table = render_table(rows)
    accounting = _baseline_accounting(hold_blow, universe, cfg)

    results = {
        "note": (
            "FAIR comparison: FPR (stable) / recall (blowup early) / median-lead, "
            "every method side by side. Operating point chosen on TUNING, reported "
            "on the held-out eval split. No operating-point tuning on the eval split."
        ),
        "eval_split": eval_split,
        "locked_test_read": lock_cfg is not None,
        "n_tuning_blowup": len(tuning_blow),
        "n_tuning_stable": len(tuning_stable),
        "n_holdout_blowup": len(hold_blow),
        "n_holdout_stable": len(hold_stable),
        "detector_operating_point": chosen,
        "operating_point_selection": selection_note,
        "tuning_grid": grid_rows,
        "stability_guard_accounting_heldout_blowup": accounting,
        "methods": {
            "detector": det_res,
            "B1_leverage_p90": b1_res,
            "B2_drawdown_velocity": b2_res,
            "B3_leverage_up_and_add": b3_res,
        },
        "fpr_budget": _FPR_BUDGET,
        "baseline_guard_x": _BASELINE_GUARD_X,
    }
    out_path.write_text(json.dumps(results, indent=2))

    # ---- console report ---------------------------------------------------
    print(f"=== eval split: {eval_split}  (locked-test read: {lock_cfg is not None}) -> {out_path.name} ===")
    print("=== DETECTOR OPERATING POINT (chosen on TUNING) ===")
    print(f"  M={cfg.M} kappa={cfg.kappa} tau={_TAU} bucket=4h burn_in={cfg.burn_in} weights=equal")
    print(f"  {selection_note}")
    print("  tuning grid (M, kappa -> FPR / recall / med-lead-h):")
    for r in grid_rows:
        mark = " <- chosen" if r["selected"] else ""
        ml = f"{r['median_lead_hours']:.0f}h" if r["median_lead_hours"] is not None else "n/a"
        print(f"    M={r['M']} k={r['kappa']:>4}: FPR={r['fpr']:.3f} recall={r['recall']:.3f} lead={ml}{mark}")
    print()
    print("=== STABILITY-GUARD ACCOUNTING (held-out blowups) ===")
    print(f"  n={accounting['n_blowup']} | excluded={accounting['excluded']} "
          f"({accounting['excluded_frac']:.1%}) | fallback={accounting['fallback']} "
          f"({accounting['fallback_frac']:.1%}) | normal={accounting['normal']}")
    print()
    print("=== FAIR COMPARISON (held-out test+val) ===")
    print(table)
    print()
    print("Reading: FPR is the fraction of STABLE masters each method falsely alerts on.")
    print("A long 'lead' next to a high FPR is not a win — the method just fires on ~everything.")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-split", choices=["val", "test", "testval"], default="testval",
                    help="held-out split to report on. Pre-lock: val. Locked read: test.")
    ap.add_argument("--out", default=None, help="output JSON path (default fair_comparison_results.json)")
    ap.add_argument("--lock-cfg", default=None,
                    help="frozen operating point 'M,kappa' for the locked-test read")
    a = ap.parse_args()
    lc = None
    if a.lock_cfg:
        parts = a.lock_cfg.split(",")
        lc = (int(parts[0]), float(parts[1]))
    main(eval_split=a.eval_split, out_path=a.out, lock_cfg=lc)
