"""Tests for the Claim A / Claim B / ablation experiment harness.

Synthetic cohorts with KNOWN structure: a 'strong' blowup master whose leverage
ramps hard (detector fires early, baselines lag) vs stable masters that never
drift. We verify the aggregate statistics behave as designed (claim_a CI excludes
0 when the detector clearly beats baselines; AUC high when blowups separate from
stable; FPR low on stable; the bootstrap resamples clusters not masters).
"""
import math

from research.hyperliquid.detector.config import (
    PrimitiveStats, PRIMITIVES, AXES, DetectorConfig,
)
from research.hyperliquid.experiments.experiment import (
    lead_time_hours,
    claim_a,
    claim_b,
    ablation,
    _bootstrap_ci_by_cluster,
    _auc,
)

H = 3600 * 1000


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def _universe_stats(mean=0.0, std=1.0, n=500):
    return {a: {p: PrimitiveStats(mean, std, n) for p in PRIMITIVES[a]} for a in AXES}


def _cfg(M=3, burn_in=5):
    return DetectorConfig(
        bucket_ms=H, M=M,
        tau={a: 0.3 for a in AXES},
        weights={a: {p: (1.0 if p == "leverage" else 0.0) for p in PRIMITIVES[a]}
                 for a in AXES},
        kappa=0, burn_in=burn_in, guard_x=0.70,
    )


def _full_cfg(M=3, burn_in=5):
    """Equal-weight config so discipline axis can also carry alerts (for ablation)."""
    return DetectorConfig(
        bucket_ms=H, M=M,
        tau={a: 0.3 for a in AXES},
        weights={a: {p: 1 / 3 for p in PRIMITIVES[a]} for a in AXES},
        kappa=0, burn_in=burn_in, guard_x=0.70,
    )


def _prims(leverage=0.0, **over):
    out = {}
    for a in AXES:
        for p in PRIMITIVES[a]:
            out[p] = 0.0
    out["leverage"] = leverage
    for k, v in over.items():
        out[k] = v
    return out


def _bucket(end_ms, equity, leverage=0.0, **over):
    return {"prim": _prims(leverage, **over), "equity": equity, "end_ms": end_ms}


def _strong_blowup_master(addr, cluster, n=60):
    """The paper's thesis case: BEHAVIORAL drift precedes equity damage.

    Equity stays flat & healthy (no drawdown -> B2 silent). Leverage holds at a low
    healthy level for a short prefix, then drifts GRADUALLY upward. The detector
    anchors to the tight early-window self-baseline (closed before the drift) and
    fires on the sustained sub-threshold elevation; B1's first-THIRD window absorbs
    early drift (high p90) so it trips LATER; B3 never fires (no loser-adds). Net:
    detector lead > best baseline lead by a few hours per master.
    blowup_time is set just past the series end (followers blow up later).
    """
    series = []
    for i in range(n):
        lev = 1.0 if i < 10 else 1.0 + 1.0 * (i - 9)  # flat prefix then gradual ramp
        series.append(_bucket((i + 1) * H, equity=100.0, leverage=lev))
    blowup_time = (n + 1) * H
    return {
        "address": addr, "label": "blowup", "split": "test",
        "blowup_time": blowup_time, "first_liq_ms": blowup_time,
        "event_cluster": cluster,
        "series": series,
    }


def _stable_master(addr, cluster, n=60):
    """Flat leverage, flat healthy equity -> no drift, detector never fires."""
    series = [_bucket((i + 1) * H, equity=100.0, leverage=2.0) for i in range(n)]
    return {
        "address": addr, "label": "stable", "split": "test",
        "blowup_time": None, "first_liq_ms": None,
        "event_cluster": cluster,
        "series": series,
    }


# ---------------------------------------------------------------------------
# lead_time_hours
# ---------------------------------------------------------------------------
def test_lead_time_basic():
    # alert 10h before blowup
    assert lead_time_hours(100 * H, 90 * H) == 10.0


def test_lead_time_none_when_alert_after_blowup():
    assert lead_time_hours(90 * H, 100 * H) is None


def test_lead_time_none_when_args_none():
    assert lead_time_hours(None, 90 * H) is None
    assert lead_time_hours(100 * H, None) is None


# ---------------------------------------------------------------------------
# _auc (Mann-Whitney)
# ---------------------------------------------------------------------------
def test_auc_perfect_separation():
    pos = [0.9, 0.8, 0.7]
    neg = [0.1, 0.2, 0.3]
    assert _auc(pos, neg) == 1.0


def test_auc_reversed():
    pos = [0.1, 0.2, 0.3]
    neg = [0.9, 0.8, 0.7]
    assert _auc(pos, neg) == 0.0


def test_auc_ties_give_half():
    pos = [0.5, 0.5]
    neg = [0.5, 0.5]
    assert _auc(pos, neg) == 0.5


def test_auc_known_value():
    pos = [1.0, 2.0]
    neg = [0.5, 1.5]
    # pairs: (1>0.5)=1, (1>1.5)=0, (2>0.5)=1, (2>1.5)=1 -> 3/4
    assert _auc(pos, neg) == 0.75


# ---------------------------------------------------------------------------
# _bootstrap_ci_by_cluster
# ---------------------------------------------------------------------------
def test_bootstrap_ci_resamples_clusters_not_masters():
    """Two clusters with very different values: resampling clusters gives a much
    wider CI than resampling the pooled 200 individual values would. We assert the
    CI spans both cluster levels (because some bootstrap draws are all-A or all-B)."""
    values_by_cluster = {
        "A": [1.0] * 100,
        "B": [100.0] * 100,
    }
    lo, hi = _bootstrap_ci_by_cluster(values_by_cluster, B=2000, seed=7)
    # median of an all-A resample is 1; all-B is 100; mixed is 1 or 100 (even split)
    assert lo <= 1.0
    assert hi >= 100.0


def test_bootstrap_ci_deterministic_under_seed():
    vbc = {"A": [1.0, 2.0, 3.0], "B": [4.0, 5.0, 6.0], "C": [7.0, 8.0, 9.0]}
    a = _bootstrap_ci_by_cluster(vbc, B=1000, seed=42)
    b = _bootstrap_ci_by_cluster(vbc, B=1000, seed=42)
    assert a == b


def test_bootstrap_ci_excludes_zero_for_all_positive():
    vbc = {"A": [5.0, 6.0, 7.0], "B": [8.0, 9.0, 10.0], "C": [5.5, 6.5]}
    lo, hi = _bootstrap_ci_by_cluster(vbc, B=2000, seed=1)
    assert lo > 0


# ---------------------------------------------------------------------------
# claim_a
# ---------------------------------------------------------------------------
def test_claim_a_detector_beats_baselines():
    """Cohort of strong blowups across several distinct events. Detector fires far
    earlier than the own-percentile / dd-velocity baselines -> positive median
    advantage with a CI that excludes 0."""
    cohort = []
    # 6 blowup masters across 3 event clusters (2 each)
    for e in range(3):
        for k in range(2):
            cohort.append(_strong_blowup_master(
                f"0x{e}{k}", cluster=f"2025-0{e+1}-01"))
    res = claim_a(cohort, _universe_stats(), _cfg())
    assert res["median_advantage"] > 0
    assert res["ci_low"] > 0  # 95% CI excludes 0
    assert res["passed"] is True
    # leave-one-event-out medians present, one per event
    assert len(res["loeo_medians"]) == 3


def test_claim_a_no_advantage_when_detector_excluded():
    """If every blowup master is already-drifting from bucket 0 (no healthy prefix),
    the early baseline excludes them -> detector lead 0 everywhere -> advantage not
    positive -> claim does not pass."""
    cohort = []
    for e in range(3):
        # leverage drifting from the very first bucket + equity sagging -> excluded
        series = []
        for i in range(60):
            eq = max(1.0, 100.0 - 2.0 * i)
            series.append(_bucket((i + 1) * H, equity=eq, leverage=5.0 + i))
        cohort.append({
            "address": f"0x{e}", "label": "blowup", "split": "test",
            "blowup_time": 80 * H, "first_liq_ms": 80 * H,
            "event_cluster": f"2025-0{e+1}-01", "series": series,
        })
    res = claim_a(cohort, _universe_stats(), _cfg())
    assert res["passed"] is False


# ---------------------------------------------------------------------------
# claim_b
# ---------------------------------------------------------------------------
def test_claim_b_discriminates_blowup_from_stable():
    cohort = []
    # 6 blowups across 3 clusters
    for e in range(3):
        for k in range(2):
            cohort.append(_strong_blowup_master(
                f"b{e}{k}", cluster=f"2025-0{e+1}-01"))
    # 8 stable across 4 clusters
    for e in range(4):
        for k in range(2):
            cohort.append(_stable_master(f"s{e}{k}", cluster=f"stable-{e}"))
    res = claim_b(cohort, _universe_stats(), _cfg())
    assert res["auc"] > 0.9
    assert res["fpr"] < 0.10          # stable masters don't early-alert
    assert res["ppv"] >= 0.30
    assert res["passed"] is True


def test_claim_b_fpr_high_when_stable_falsely_alert():
    """A degenerate baseline where stable masters look like blowups should NOT pass
    the FPR gate. We simulate this by making 'stable' masters actually drift."""
    cohort = []
    for e in range(2):
        for k in range(2):
            cohort.append(_strong_blowup_master(f"b{e}{k}", cluster=f"ev-{e}"))
    # mislabeled 'stable' masters that actually ramp -> they early-alert -> FPR high
    for e in range(4):
        m = _strong_blowup_master(f"s{e}", cluster=f"st-{e}")
        m["label"] = "stable"
        m["blowup_time"] = None
        m["first_liq_ms"] = None
        cohort.append(m)
    res = claim_b(cohort, _universe_stats(), _cfg())
    assert res["fpr"] >= 0.10
    assert res["passed"] is False


# ---------------------------------------------------------------------------
# ablation
# ---------------------------------------------------------------------------
def test_ablation_reports_ratio_and_ci():
    """Discipline-only vs full detector on blowups that drift on ALL axes (so the
    discipline axis carries evidence too). Reports a ratio and an event-clustered
    CI on the discipline-only lead."""
    cohort = []
    n = 60
    for e in range(3):
        for k in range(2):
            # flat healthy equity; gradual drift on BOTH exposure (leverage UP) and
            # discipline (stop_attach_rate DOWN) so the discipline-only detector can
            # also accumulate evidence and lead the blowup.
            series = []
            for i in range(n):
                if i < 10:
                    lev, stop = 1.0, 1.0
                else:
                    lev = 1.0 + 1.0 * (i - 9)            # exposure drift up
                    stop = max(0.0, 1.0 - 0.08 * (i - 9))  # discipline drift down
                series.append(_bucket((i + 1) * H, equity=100.0,
                                      leverage=lev, stop_attach_rate=stop))
            cohort.append({
                "address": f"a{e}{k}", "label": "blowup", "split": "test",
                "blowup_time": (n + 1) * H, "first_liq_ms": (n + 1) * H,
                "event_cluster": f"2025-0{e+1}-01", "series": series,
            })
    res = ablation(cohort, _universe_stats(), _full_cfg())
    assert "lead_ratio" in res
    assert "disc_ci_low" in res and "disc_ci_high" in res
    # discipline-only detector should achieve a positive lead CI on this cohort
    assert res["disc_ci_low"] > 0


def test_ablation_handles_no_discipline_detection():
    """If discipline never fires (exposure-only drift, discipline axis flat), the
    discipline-only leads are all 0; ratio is reported, CI does not exclude 0."""
    cohort = []
    for e in range(2):
        for k in range(2):
            cohort.append(_strong_blowup_master(f"x{e}{k}", cluster=f"ev-{e}"))
    res = ablation(cohort, _universe_stats(), _full_cfg())
    # discipline-only leads should be ~0 (no discipline drift) -> CI includes 0
    assert res["disc_ci_low"] <= 0
