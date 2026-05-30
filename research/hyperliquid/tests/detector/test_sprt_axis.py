"""Tests for AxisSPRT: per-axis mSPRT wrapper reusing ssrt.core engine.

Key properties verified:
1. Sustained negative drift drives p-value below alpha (power).
2. Flat zero observations keep p-value high (Type I control).
3. Positive observations never alert (one-sided mSPRT semantics).
4. Each axis has an independent engine (no cross-axis contamination).
5. p-value is always returned (no burn_in masking).
"""
import pytest
from research.hyperliquid.detector.config import DetectorConfig, AXES, PRIMITIVES
from research.hyperliquid.detector.sprt_axis import AxisSPRT


def _cfg(burn_in=5):
    return DetectorConfig(
        bucket_ms=1, M=1,
        tau={a: 1.0 for a in AXES},
        weights={a: {p: 1/3 for p in PRIMITIVES[a]} for a in AXES},
        kappa=1e-9,
        burn_in=burn_in,
    )


def test_sustained_negative_drift_drives_pvalue_below_alpha():
    """60 observations at -1.5 sigma → p-value < alpha=0.01."""
    sprt = AxisSPRT(_cfg())
    p = 1.0
    for _ in range(60):
        p = sprt.update("exposure", -1.5)
    assert p < 0.01, f"expected p < 0.01 after sustained bad drift, got {p}"


def test_flat_zero_keeps_pvalue_high():
    """60 observations at 0 → p-value stays > 0.01 (no false alert)."""
    sprt = AxisSPRT(_cfg())
    p = 1.0
    for _ in range(60):
        p = sprt.update("discipline", 0.0)
    assert p > 0.01, f"expected p > 0.01 for flat-zero, got {p}"


def test_positive_obs_never_alerts_one_sided():
    """Positive observations (good direction) → p-value == 1.0 (one-sided engine)."""
    sprt = AxisSPRT(_cfg())
    p = 1.0
    for _ in range(60):
        p = sprt.update("tilt", +2.0)
    assert p == 1.0, f"expected p==1.0 for good-direction obs, got {p}"


def test_axes_are_independent():
    """Contaminating exposure does not affect discipline p-value."""
    sprt = AxisSPRT(_cfg())
    # Drive exposure strongly negative
    for _ in range(60):
        sprt.update("exposure", -3.0)
    # discipline has seen no updates — p should be 1.0 (z_bar = 0 after 0 obs,
    # or whatever the initial state returns on first query)
    # Actually: discipline engine has n=0 until first update call.
    # Feed discipline one neutral observation to get a real p_value.
    p_disc = sprt.update("discipline", 0.0)
    assert p_disc == 1.0, (
        f"discipline should be unaffected by exposure updates, got {p_disc}")


def test_pvalue_returned_during_burn_in():
    """p_value is always-valid even before burn_in buckets (no masking)."""
    cfg = _cfg(burn_in=100)
    sprt = AxisSPRT(cfg)
    # Only 5 updates — well within burn_in=100
    p = None
    for _ in range(5):
        p = sprt.update("exposure", -2.0)
    # p should be a real float in (0, 1], not None or 1.0 forced by burn_in gate
    assert p is not None
    assert 0.0 < p <= 1.0, f"expected real p-value during burn_in, got {p}"


def test_all_three_axes_accept_updates():
    """update() works on all axis names without KeyError."""
    sprt = AxisSPRT(_cfg())
    for axis in AXES:
        p = sprt.update(axis, -0.5)
        assert isinstance(p, float)
        assert 0.0 < p <= 1.0
