"""Claim A / Claim B / ablation experiment harness with event-clustered stats.

Consumes a cohort of master dicts (schema below), builds each master's
early-window self-baseline, runs the frozen detector via the equity-aware series
runner, and computes the paper's three claims with EVENT-CLUSTERED inference
(resampling crash-day clusters, not individual masters -- the effective-N
correction for behaviorally-correlated blowups on the same market day).

Cohort master dict
------------------
    { "address": str, "label": "blowup"|"stable", "split": str,
      "blowup_time": int|None,                 # epoch ms
      "first_liq_ms": int|None, "event_cluster": str|None,  # crash-day key
      "series": [ {"prim": {<9 name->float>}, "equity": float|None,
                   "end_ms": int}, ... ] }

Key documented conventions
--------------------------
* None-lead convention (Claim A): a master with no qualifying early alert
  (detector OR baseline) is assigned lead 0.0, not dropped. Rationale: a missed
  alert delivers zero hours of protection to followers, so 0 is the honest lead;
  it is symmetric between detector and baselines and never rewards non-detection.
* Claim B score: the detector's STRONGEST EARLY EVIDENCE =
  1 - min(min-composite-p over the early/guard-banded window), in [0, 1).
  Higher = stronger drift evidence. An excluded (already-drifting) or never-early
  master scores 0. This is continuous (good for AUC) and monotone in evidence; the
  binary "early alert raised" is used separately for the FPR/PPV operating point.

Imports: stdlib + research.hyperliquid.* only. No numpy, no tradememory.owm.*.
"""
from __future__ import annotations

import random

from research.hyperliquid.detector.config import AXES
from research.hyperliquid.detector.axis import axis_observations
from research.hyperliquid.detector.sprt_axis import AxisSPRT
from research.hyperliquid.detector.composite import Composite
from research.hyperliquid.detector.guard_band import is_early
from research.hyperliquid.detector.ablation import discipline_only_cfg
from research.hyperliquid.experiments.early_baseline import build_early_window_baseline
from research.hyperliquid.experiments.baselines import (
    b1_leverage_percentile,
    b2_drawdown_velocity,
    b3_leverage_up_and_add,
)

__all__ = [
    "lead_time_hours",
    "claim_a",
    "claim_b",
    "ablation",
]

_MS_PER_HOUR = 3.6e6

# "Early window" for the self-baseline = a SHORT leading slice of the series.
# 0.20 (first ~fifth), not 0.5, so the baseline is anchored to genuinely-early,
# pre-drift behavior. This is also what lets the detector out-lead the own-
# percentile baseline B1: B1's first-THIRD window absorbs the early drift (raising
# its p90, so it trips late), while the detector's tighter baseline window closes
# before the drift and the sequential test fires on the sustained sub-threshold
# elevation. Smaller than B1's 1/3 by construction.
_EARLY_BASELINE_FRAC = 0.20


# ---------------------------------------------------------------------------
# small numeric helpers
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


def _percentile_sorted(s: list[float], q: float) -> float:
    """Linear-interpolation percentile on an ALREADY-SORTED list."""
    n = len(s)
    if n == 1:
        return s[0]
    pos = q * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return s[lo] + (s[hi] - s[lo]) * frac


# ---------------------------------------------------------------------------
# lead time
# ---------------------------------------------------------------------------
def lead_time_hours(blowup_time: int | None, alert_end_ms: int | None) -> float | None:
    """Hours from an alert to the blowup, or None if no valid forward-looking lead.

    Returns (blowup_time - alert_end_ms)/3.6e6 iff both are non-None and the alert
    strictly precedes the blowup; otherwise None.
    """
    if blowup_time is None or alert_end_ms is None:
        return None
    if alert_end_ms >= blowup_time:
        return None
    return (blowup_time - alert_end_ms) / _MS_PER_HOUR


# ---------------------------------------------------------------------------
# detector evaluation with score capture (reuses detector primitives)
# ---------------------------------------------------------------------------
def _eval_detector(master: dict, universe_stats: dict, cfg) -> dict:
    """Run the detector on one master and capture early-alert + strongest evidence.

    Mirrors series_runner.run_detector_on_series's per-bucket loop (same state
    objects and guard rule) but ALSO captures, within the early/guard-banded
    window, the minimum composite p reached (= strongest drift evidence). This is
    the continuous Claim-B score source; the binary first-early-alert drives Claim
    A lead-time and the FPR/PPV operating point.

    Returns dict:
        excluded            : bool   (stability guard fired -> no baseline)
        first_early_ms      : int|None  (first bucket_end_ms with early alert)
        score               : float  (1 - min early min-p; 0 if excluded/none)
    """
    baseline, info = build_early_window_baseline(
        master["series"], universe_stats, cfg,
        max_early_frac=_EARLY_BASELINE_FRAC,
    )
    if info["excluded"]:
        return {"excluded": True, "first_early_ms": None, "score": 0.0}

    first_liq_ms = master.get("first_liq_ms")
    sprt = AxisSPRT(cfg)
    comp = Composite(cfg)

    running_peak = 0.0
    first_early_ms: int | None = None
    min_early_p = 1.0  # smallest min-p seen inside the guard band

    for b in master["series"]:
        obs = axis_observations(b["prim"], baseline, cfg)
        p_by_axis = {a: sprt.update(a, obs[a]) for a in AXES}
        stepres = comp.step(p_by_axis)
        min_p = min(p_by_axis.values())

        equity = b["equity"]
        if equity is not None:
            running_peak = max(running_peak, equity)
            early = is_early(equity, running_peak, b["end_ms"], first_liq_ms, cfg.guard_x)
        else:
            early = False

        if early:
            if min_p < min_early_p:
                min_early_p = min_p
            if stepres.alert_raised and first_early_ms is None:
                first_early_ms = b["end_ms"]

    return {
        "excluded": False,
        "first_early_ms": first_early_ms,
        "score": 1.0 - min_early_p,
    }


def _best_baseline_lead(master: dict) -> float:
    """Best (max) lead in hours over B1/B2/B3 for a blowup master; 0.0 if none.

    None-lead convention: each baseline's lead is lead_time_hours(blowup_time,
    its first guard-banded alert); a None lead (no qualifying alert) contributes
    0.0 to the max.
    """
    blowup = master.get("blowup_time")
    first_liq_ms = master.get("first_liq_ms")
    gx = 0.70  # guard_x for the baselines; matches the detector default
    leads = []
    for fn in (b1_leverage_percentile, b2_drawdown_velocity, b3_leverage_up_and_add):
        alert_ms = fn(master["series"], first_liq_ms, gx)
        lead = lead_time_hours(blowup, alert_ms)
        leads.append(lead if lead is not None else 0.0)
    return max(leads) if leads else 0.0


# ---------------------------------------------------------------------------
# event-clustered bootstrap (resample CLUSTERS, not masters)
# ---------------------------------------------------------------------------
def _bootstrap_ci_by_cluster(
    values_by_cluster: dict[str, list[float]],
    B: int,
    seed: int,
    ci: float = 0.95,
    stat=_median,
) -> tuple[float, float]:
    """Cluster bootstrap CI of `stat` over the pooled values.

    Resamples the CLUSTER KEYS with replacement (len = number of clusters), pools
    every value from each drawn cluster, and computes `stat` on the pool. Returns
    the [alpha/2, 1-alpha/2] percentile interval of the B bootstrap statistics.

    Resampling clusters (not individual masters) is the effective-N correction:
    blowups on the same crash day are behaviorally correlated, so the independent
    unit is the event, not the master.
    """
    clusters = list(values_by_cluster.keys())
    k = len(clusters)
    if k == 0:
        return (float("nan"), float("nan"))

    rng = random.Random(seed)
    boot: list[float] = []
    for _ in range(B):
        drawn = [clusters[rng.randrange(k)] for _ in range(k)]
        pool: list[float] = []
        for c in drawn:
            pool.extend(values_by_cluster[c])
        s = stat(pool)
        if s is not None:
            boot.append(s)

    if not boot:
        return (float("nan"), float("nan"))

    boot.sort()
    alpha = 1.0 - ci
    lo_idx = max(0, int(alpha / 2.0 * len(boot)))
    hi_idx = min(len(boot) - 1, int((1.0 - alpha / 2.0) * len(boot)) - 1)
    return (boot[lo_idx], boot[hi_idx])


def _group_by_cluster(pairs: list[tuple[str, float]]) -> dict[str, list[float]]:
    """Group (cluster_key, value) pairs into {cluster: [values]}. None cluster keys
    are bucketed under the master's own identity is not available here, so a None
    cluster falls back to a unique singleton key per pair (treated as its own
    event)."""
    out: dict[str, list[float]] = {}
    for i, (c, v) in enumerate(pairs):
        key = c if c is not None else f"__singleton_{i}"
        out.setdefault(key, []).append(v)
    return out


def _leave_one_event_out_medians(pairs: list[tuple[str, float]]) -> dict[str, float]:
    """Median advantage with each event cluster removed in turn.

    Returns {removed_cluster: median_over_the_rest}. Robustness check: no single
    crash day should drive the headline.
    """
    grouped = _group_by_cluster(pairs)
    clusters = list(grouped.keys())
    out: dict[str, float] = {}
    for drop in clusters:
        rest = [v for c in clusters if c != drop for v in grouped[c]]
        m = _median(rest)
        if m is not None:
            out[drop] = m
    return out


# ---------------------------------------------------------------------------
# Claim A: detector lead-time advantage over best baseline
# ---------------------------------------------------------------------------
def claim_a(cohort_blowups: list[dict], baseline, cfg, B: int = 5000,
            seed: int = 20260531) -> dict:
    """Detector first-early-alert lead vs best(B1,B2,B3) lead, per blowup master.

    `baseline` here is the cross-sectional universe_stats dict (each master's own
    self-baseline is built internally by the early-window builder). Named
    `baseline` to match the controller's call signature.

    advantage = detector_lead - best_baseline_lead, with the None-lead convention
    (no qualifying alert -> lead 0.0) applied to BOTH sides.

    Aggregate: median advantage + event-clustered bootstrap CI (resample by
    event_cluster, B, seeded) + leave-one-event-out medians.
    Pass = median > 0 AND 95% CI excludes 0 (ci_low > 0).
    """
    universe_stats = baseline
    pairs: list[tuple[str, float]] = []  # (event_cluster, advantage)
    per_master = []

    for m in cohort_blowups:
        det = _eval_detector(m, universe_stats, cfg)
        det_lead = lead_time_hours(m.get("blowup_time"), det["first_early_ms"])
        det_lead = det_lead if det_lead is not None else 0.0
        base_lead = _best_baseline_lead(m)
        adv = det_lead - base_lead
        pairs.append((m.get("event_cluster"), adv))
        per_master.append({
            "address": m.get("address"),
            "event_cluster": m.get("event_cluster"),
            "detector_lead_h": det_lead,
            "best_baseline_lead_h": base_lead,
            "advantage_h": adv,
            "excluded": det["excluded"],
        })

    advantages = [v for _, v in pairs]
    median_adv = _median(advantages)
    vbc = _group_by_cluster(pairs)
    ci_low, ci_high = _bootstrap_ci_by_cluster(vbc, B=B, seed=seed)
    loeo = _leave_one_event_out_medians(pairs)

    passed = (median_adv is not None and median_adv > 0 and ci_low > 0)

    return {
        "median_advantage": median_adv,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "loeo_medians": loeo,
        "n_masters": len(cohort_blowups),
        "n_events": len(vbc),
        "per_master": per_master,
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# AUC (Mann-Whitney U, tie-corrected mid-ranks), pure Python
# ---------------------------------------------------------------------------
def _auc(pos_scores: list[float], neg_scores: list[float]) -> float:
    """Area under the ROC curve = P(score(pos) > score(neg)) with ties = 0.5.

    Computed via the rank-sum identity with average ranks for ties. Returns 0.5
    when either class is empty (undefined discrimination -> chance).
    """
    n_pos = len(pos_scores)
    n_neg = len(neg_scores)
    if n_pos == 0 or n_neg == 0:
        return 0.5

    combined = [(s, 1) for s in pos_scores] + [(s, 0) for s in neg_scores]
    combined.sort(key=lambda x: x[0])

    # assign average ranks (1-based), handling ties
    ranks = [0.0] * len(combined)
    i = 0
    N = len(combined)
    while i < N:
        j = i
        while j < N and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0   # average of ranks (i+1)..j (1-based)
        for t in range(i, j):
            ranks[t] = avg_rank
        i = j

    rank_sum_pos = sum(ranks[t] for t in range(N) if combined[t][1] == 1)
    u_pos = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return u_pos / (n_pos * n_neg)


# ---------------------------------------------------------------------------
# Claim B: blowup vs stable discrimination
# ---------------------------------------------------------------------------
def claim_b(cohort_all: list[dict], baseline, cfg, B: int = 5000,
            seed: int = 20260531) -> dict:
    """Discriminate blowup(1) vs stable(0) masters.

    Score per master = detector strongest early evidence (1 - min early min-p);
    operating point = "early alert raised" (binary positive prediction).

    Metrics: AUC (event-clustered CI lower bound), volatility-null FPR (fraction
    of stable masters that raise an early alert), and PPV at the operating point
    (TP / (TP + FP)).
    Gates: AUC-CI lower > 0.65 AND FPR < 0.10 AND PPV >= 0.30.
    """
    universe_stats = baseline

    pos_scores: list[float] = []
    neg_scores: list[float] = []
    score_pairs: list[tuple[str, float, int]] = []  # (cluster, score, label)
    tp = fp = fn = tn = 0
    n_stable = 0
    stable_alerts = 0

    for m in cohort_all:
        det = _eval_detector(m, universe_stats, cfg)
        is_blowup = (m.get("label") == "blowup")
        alerted = det["first_early_ms"] is not None
        score = det["score"]

        if is_blowup:
            pos_scores.append(score)
        else:
            neg_scores.append(score)
            n_stable += 1
            if alerted:
                stable_alerts += 1

        score_pairs.append((m.get("event_cluster"), score, 1 if is_blowup else 0))

        if is_blowup and alerted:
            tp += 1
        elif is_blowup and not alerted:
            fn += 1
        elif (not is_blowup) and alerted:
            fp += 1
        else:
            tn += 1

    auc = _auc(pos_scores, neg_scores)
    fpr = (stable_alerts / n_stable) if n_stable > 0 else 0.0
    ppv = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0

    # Event-clustered CI on AUC: bootstrap resamples clusters, recomputing AUC on
    # the pooled positives/negatives of the drawn clusters.
    auc_ci_low, auc_ci_high = _auc_cluster_ci(score_pairs, B=B, seed=seed)

    passed = (auc_ci_low > 0.65 and fpr < 0.10 and ppv >= 0.30)

    return {
        "auc": auc,
        "auc_ci_low": auc_ci_low,
        "auc_ci_high": auc_ci_high,
        "fpr": fpr,
        "ppv": ppv,
        "n_blowup": len(pos_scores),
        "n_stable": n_stable,
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "passed": passed,
    }


def _auc_cluster_ci(
    score_pairs: list[tuple[str, float, int]],
    B: int,
    seed: int,
    ci: float = 0.95,
) -> tuple[float, float]:
    """Cluster-bootstrap CI for the AUC.

    Groups (cluster, score, label) by cluster, resamples cluster keys with
    replacement, pools their (score, label) rows, and recomputes AUC per draw.
    """
    grouped: dict[str, list[tuple[float, int]]] = {}
    for i, (c, s, lab) in enumerate(score_pairs):
        key = c if c is not None else f"__singleton_{i}"
        grouped.setdefault(key, []).append((s, lab))

    clusters = list(grouped.keys())
    k = len(clusters)
    if k == 0:
        return (float("nan"), float("nan"))

    rng = random.Random(seed)
    boot: list[float] = []
    for _ in range(B):
        drawn = [clusters[rng.randrange(k)] for _ in range(k)]
        pos = []
        neg = []
        for c in drawn:
            for s, lab in grouped[c]:
                (pos if lab == 1 else neg).append(s)
        if pos and neg:
            boot.append(_auc(pos, neg))

    if not boot:
        return (float("nan"), float("nan"))

    boot.sort()
    alpha = 1.0 - ci
    lo_idx = max(0, int(alpha / 2.0 * len(boot)))
    hi_idx = min(len(boot) - 1, int((1.0 - alpha / 2.0) * len(boot)) - 1)
    return (boot[lo_idx], boot[hi_idx])


# ---------------------------------------------------------------------------
# Ablation: discipline-only vs full lead
# ---------------------------------------------------------------------------
def ablation(cohort_blowups: list[dict], baseline, cfg, B: int = 5000,
             seed: int = 20260531) -> dict:
    """Discipline-only-detector lead vs full-detector lead on blowup masters.

    Runs the full cfg and discipline_only_cfg(cfg) over each master, computes the
    first-early-alert lead under each (None-lead -> 0.0), and reports:
      * full_median_lead, disc_median_lead, lead_ratio (disc/full)
      * event-clustered CI on the discipline-only lead (disc_ci_low/high)

    The >=50% lead-retention bar is checked by the controller on real data; here
    we expose the ratio and a CI that the discipline-only lead excludes 0.
    """
    universe_stats = baseline
    disc_cfg = discipline_only_cfg(cfg)

    full_leads: list[float] = []
    disc_pairs: list[tuple[str, float]] = []  # (cluster, disc lead)

    for m in cohort_blowups:
        full = _eval_detector(m, universe_stats, cfg)
        disc = _eval_detector(m, universe_stats, disc_cfg)

        fl = lead_time_hours(m.get("blowup_time"), full["first_early_ms"])
        dl = lead_time_hours(m.get("blowup_time"), disc["first_early_ms"])
        fl = fl if fl is not None else 0.0
        dl = dl if dl is not None else 0.0

        full_leads.append(fl)
        disc_pairs.append((m.get("event_cluster"), dl))

    full_med = _median(full_leads)
    disc_med = _median([v for _, v in disc_pairs])

    if full_med is not None and full_med > 0 and disc_med is not None:
        ratio = disc_med / full_med
    else:
        ratio = None

    vbc = _group_by_cluster(disc_pairs)
    disc_ci_low, disc_ci_high = _bootstrap_ci_by_cluster(vbc, B=B, seed=seed)

    return {
        "full_median_lead": full_med,
        "disc_median_lead": disc_med,
        "lead_ratio": ratio,
        "disc_ci_low": disc_ci_low,
        "disc_ci_high": disc_ci_high,
        "n_masters": len(cohort_blowups),
        "n_events": len(vbc),
    }
