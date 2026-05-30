"""Tests for axis_observations: z-score composition + sign convention.

Sign convention (BAD_DIR in config.py):
  exposure  BAD_DIR=+1  → exposure z > 0 is bad → multiply by -1 → bad = obs < 0
  discipline BAD_DIR=-1 → discipline z < 0 is bad → multiply by +1 → bad = obs < 0
  tilt      BAD_DIR=+1  → tilt z > 0 is bad → multiply by -1 → bad = obs < 0

All axes therefore feed the one-sided mSPRT (null_mean=0) with bad = mean below 0.

kappa=1e-9 with n=10_000 → w = n/(n+kappa) ≈ 1.0 → pure self-stats.
"""
import pytest
from research.hyperliquid.detector.config import (
    PrimitiveStats, BaselineStats, DetectorConfig, PRIMITIVES, AXES)
from research.hyperliquid.detector.axis import axis_observations


def _flat_baseline(mean=0.0, std=1.0, n=10_000):
    """All primitives have the same mean/std in both self and universe."""
    self_stats = {a: {p: PrimitiveStats(mean, std, n) for p in PRIMITIVES[a]} for a in AXES}
    univ = {a: {p: PrimitiveStats(0.0, 1.0, 9999) for p in PRIMITIVES[a]} for a in AXES}
    return BaselineStats(self_stats, univ)


def _cfg():
    # kappa=1e-9: w = n/(n+kappa) ≈ 1.0 → pure self-stats, z = value
    return DetectorConfig(
        bucket_ms=1, M=1,
        tau={a: 0.3 for a in AXES},
        weights={a: {p: 1/3 for p in PRIMITIVES[a]} for a in AXES},
        kappa=1e-9,
    )


def test_exposure_up_yields_negative_signed_obs():
    """Exposure primitives at +3 sigma (bad) → signed obs < 0 (sign-flipped)."""
    base = _flat_baseline()
    vals = {p: 0.0 for a in AXES for p in PRIMITIVES[a]}
    for p in PRIMITIVES["exposure"]:
        vals[p] = 3.0   # +3 sigma exposure = BAD
    obs = axis_observations(vals, base, _cfg())
    assert obs["exposure"] < 0, f"expected exposure < 0, got {obs['exposure']}"


def test_discipline_down_yields_negative_signed_obs():
    """Discipline primitives at -2 sigma (bad = dropped) → signed obs < 0."""
    base = _flat_baseline()
    vals = {p: 0.0 for a in AXES for p in PRIMITIVES[a]}
    for p in PRIMITIVES["discipline"]:
        vals[p] = -2.0  # discipline dropped = BAD
    obs = axis_observations(vals, base, _cfg())
    assert obs["discipline"] < 0, f"expected discipline < 0, got {obs['discipline']}"


def test_tilt_up_yields_negative_signed_obs():
    """Tilt primitives at +2 sigma (bad) → signed obs < 0 (sign-flipped)."""
    base = _flat_baseline()
    vals = {p: 0.0 for a in AXES for p in PRIMITIVES[a]}
    for p in PRIMITIVES["tilt"]:
        vals[p] = 2.0   # +2 sigma tilt = BAD
    obs = axis_observations(vals, base, _cfg())
    assert obs["tilt"] < 0, f"expected tilt < 0, got {obs['tilt']}"


def test_zero_input_at_mean_yields_zero_obs():
    """All primitives at baseline mean → z=0 → signed obs = 0 for all axes."""
    base = _flat_baseline()
    vals = {p: 0.0 for a in AXES for p in PRIMITIVES[a]}
    obs = axis_observations(vals, base, _cfg())
    for axis in AXES:
        assert abs(obs[axis]) < 1e-12, f"expected {axis} ≈ 0, got {obs[axis]}"


def test_discipline_good_direction_is_positive():
    """Discipline primitives above mean (good = higher discipline) → obs > 0."""
    base = _flat_baseline()
    vals = {p: 0.0 for a in AXES for p in PRIMITIVES[a]}
    for p in PRIMITIVES["discipline"]:
        vals[p] = 2.0   # discipline up = GOOD
    obs = axis_observations(vals, base, _cfg())
    assert obs["discipline"] > 0, f"expected discipline > 0 (good), got {obs['discipline']}"


def test_all_axes_returned():
    """axis_observations returns exactly the three axes."""
    base = _flat_baseline()
    vals = {p: 0.0 for a in AXES for p in PRIMITIVES[a]}
    obs = axis_observations(vals, base, _cfg())
    assert set(obs.keys()) == set(AXES)


def test_weighted_sum_magnitude():
    """With equal weights (1/3) and pure self-stats (kappa≈0),
    3 primitives all at +1 sigma → weighted sum = 1.0; sign-flip for exposure → -1.0."""
    base = _flat_baseline()
    vals = {p: 0.0 for a in AXES for p in PRIMITIVES[a]}
    for p in PRIMITIVES["exposure"]:
        vals[p] = 1.0
    obs = axis_observations(vals, base, _cfg())
    assert abs(obs["exposure"] - (-1.0)) < 1e-9, f"expected -1.0, got {obs['exposure']}"


def test_nonzero_other_axes_isolated():
    """Perturbing only exposure primitives does not change discipline/tilt obs."""
    base = _flat_baseline()
    vals = {p: 0.0 for a in AXES for p in PRIMITIVES[a]}
    for p in PRIMITIVES["exposure"]:
        vals[p] = 5.0
    obs = axis_observations(vals, base, _cfg())
    assert abs(obs["discipline"]) < 1e-12
    assert abs(obs["tilt"]) < 1e-12
