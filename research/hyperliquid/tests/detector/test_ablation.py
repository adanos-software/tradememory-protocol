"""Tests for the discipline-only ablation harness (Task 16).

Covers:
1. mask_axes backward-compat: existing DetectorConfig(...) calls unaffected.
2. mask_axes validation: invalid axis name raises ValueError.
3. discipline_only_cfg: mask_axes == {"exposure","tilt"}, other fields unchanged.
4. AxisSPRT mask: masked axis always returns 1.0 regardless of observation.
5. ablation_sanity scenario A: CI excludes 0 (discipline-only detector detects
   discipline-only drift).
"""
import pytest

from research.hyperliquid.detector.config import DetectorConfig, AXES, PRIMITIVES
from research.hyperliquid.detector.sprt_axis import AxisSPRT
from research.hyperliquid.tests.detector.helpers import anchors_flat, identity_cov


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _full_cfg(**overrides):
    base = dict(
        bucket_ms=1,
        M=3,
        tau={a: 0.3 for a in AXES},
        weights={a: {p: 1 / 3 for p in PRIMITIVES[a]} for a in AXES},
        kappa=0,
        burn_in=10,
    )
    base.update(overrides)
    return DetectorConfig(**base)


# ---------------------------------------------------------------------------
# 1. mask_axes backward-compat
# ---------------------------------------------------------------------------

def test_config_without_mask_axes_still_works():
    """Omitting mask_axes defaults to frozenset() — all existing call sites unaffected."""
    cfg = _full_cfg()
    assert cfg.mask_axes == frozenset()


def test_config_with_valid_mask_axes():
    cfg = _full_cfg(mask_axes=frozenset({"exposure", "tilt"}))
    assert cfg.mask_axes == frozenset({"exposure", "tilt"})


def test_config_with_empty_mask_axes():
    cfg = _full_cfg(mask_axes=frozenset())
    assert cfg.mask_axes == frozenset()


# ---------------------------------------------------------------------------
# 2. mask_axes validation
# ---------------------------------------------------------------------------

def test_config_rejects_invalid_mask_axis():
    with pytest.raises(ValueError, match="mask_axes contains invalid axes"):
        _full_cfg(mask_axes=frozenset({"fake_axis"}))


def test_config_rejects_partial_invalid_mask_axes():
    with pytest.raises(ValueError, match="mask_axes contains invalid axes"):
        _full_cfg(mask_axes=frozenset({"exposure", "bad"}))


# ---------------------------------------------------------------------------
# 3. discipline_only_cfg
# ---------------------------------------------------------------------------

def test_discipline_only_cfg_sets_correct_mask():
    from research.hyperliquid.detector.ablation import discipline_only_cfg
    base = _full_cfg()
    disc = discipline_only_cfg(base)
    assert disc.mask_axes == frozenset({"exposure", "tilt"})


def test_discipline_only_cfg_preserves_other_fields():
    from research.hyperliquid.detector.ablation import discipline_only_cfg
    base = _full_cfg(M=5, burn_in=15, kappa=7.0, alpha=0.05)
    disc = discipline_only_cfg(base)
    assert disc.M == 5
    assert disc.burn_in == 15
    assert disc.kappa == 7.0
    assert disc.alpha == 0.05
    assert disc.bucket_ms == base.bucket_ms
    assert disc.tau == base.tau
    assert disc.weights == base.weights


# ---------------------------------------------------------------------------
# 4. AxisSPRT mask forces p-value to 1.0
# ---------------------------------------------------------------------------

def test_mask_forces_axis_pvalue_high():
    """Masked axes never contribute evidence — p-value is pinned at 1.0."""
    cfg = DetectorConfig(
        bucket_ms=1, M=1,
        tau={a: 1.0 for a in AXES},
        weights={a: {p: 1 / 3 for p in PRIMITIVES[a]} for a in AXES},
        kappa=0,
        burn_in=1,
        mask_axes=frozenset({"exposure", "tilt"}),
    )
    sprt = AxisSPRT(cfg)
    p_exp = 1.0
    for _ in range(30):
        p_exp = sprt.update("exposure", -3.0)   # strong bad signal, but masked
    assert p_exp == 1.0, f"masked axis must return 1.0, got {p_exp}"

    p_tilt = 1.0
    for _ in range(30):
        p_tilt = sprt.update("tilt", -3.0)
    assert p_tilt == 1.0, f"masked tilt must return 1.0, got {p_tilt}"


def test_unmasked_axis_still_drives_below_alpha():
    """After masking exposure+tilt, the discipline axis still works normally."""
    cfg = DetectorConfig(
        bucket_ms=1, M=1,
        tau={a: 1.0 for a in AXES},
        weights={a: {p: 1 / 3 for p in PRIMITIVES[a]} for a in AXES},
        kappa=0,
        burn_in=1,
        mask_axes=frozenset({"exposure", "tilt"}),
    )
    sprt = AxisSPRT(cfg)
    p_disc = 1.0
    for _ in range(60):
        p_disc = sprt.update("discipline", -3.0)
    assert p_disc < 0.01, f"unmasked discipline should alert, got {p_disc}"


def test_no_mask_all_axes_contribute():
    """With no mask, all axes accumulate evidence normally."""
    cfg = _full_cfg(burn_in=1)
    sprt = AxisSPRT(cfg)
    for axis in AXES:
        p = 1.0
        for _ in range(60):
            p = sprt.update(axis, -3.0)
        assert p < 0.01, f"axis {axis} should alert with no mask, got {p}"


# ---------------------------------------------------------------------------
# 5. ablation_sanity: Scenario A CI excludes 0
# ---------------------------------------------------------------------------

def test_scenario_A_discipline_only_recovers_measurable_lead():
    """Discipline-only detector CI excludes 0 -> the harness can measure the bar."""
    from research.hyperliquid.detector.ablation import ablation_sanity
    cfg = _full_cfg(M=3, burn_in=10)
    res = ablation_sanity(
        anchors_flat(),
        identity_cov(),
        cfg,
        seed=5,
        n_streams=60,
        length=300,
    )
    sc_a = res["scenario_A"]
    ci_low = sc_a["ci_low"]
    assert ci_low > 0, (
        f"Scenario A CI should exclude 0, got ci_low={ci_low}, "
        f"ci_high={sc_a['ci_high']}, median={sc_a['median']}, "
        f"disc_power={sc_a['disc_power']}"
    )


def test_ablation_sanity_returns_all_scenarios():
    from research.hyperliquid.detector.ablation import ablation_sanity
    cfg = _full_cfg(M=2, burn_in=5)
    res = ablation_sanity(
        anchors_flat(),
        identity_cov(),
        cfg,
        seed=42,
        n_streams=20,
        length=100,
    )
    assert "scenario_A" in res
    assert "scenario_B" in res
    assert "scenario_C" in res
    for key in ("full_power", "disc_power"):
        assert key in res["scenario_A"]
        assert key in res["scenario_B"]
        assert key in res["scenario_C"]
    # scenario_A must have CI keys
    for key in ("ci_low", "ci_high", "median", "disc_to_full_latency_ratio"):
        assert key in res["scenario_A"], f"missing key {key!r} in scenario_A"


def test_ablation_sanity_deterministic():
    """Same seed -> same results."""
    from research.hyperliquid.detector.ablation import ablation_sanity
    cfg = _full_cfg(M=2, burn_in=5)
    res1 = ablation_sanity(anchors_flat(), identity_cov(), cfg, seed=1, n_streams=10, length=80)
    res2 = ablation_sanity(anchors_flat(), identity_cov(), cfg, seed=1, n_streams=10, length=80)
    assert res1["scenario_A"]["ci_low"] == res2["scenario_A"]["ci_low"]
    assert res1["scenario_A"]["disc_power"] == res2["scenario_A"]["disc_power"]
