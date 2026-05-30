"""Axis composition: per-primitive shrinkage z-score → weighted sum → sign convention.

For each axis, compute a signed scalar observation suitable for the one-sided
mSPRT engine (MixtureSPRT with null_mean=0).  The sign convention is:

  - exposure  (BAD_DIR=+1): bad drift = primitives UP → z > 0 → multiply by -1
  - discipline (BAD_DIR=-1): bad drift = primitives DOWN → z < 0 → multiply by +1
  - tilt      (BAD_DIR=+1): bad drift = primitives UP → z > 0 → multiply by -1

After the sign flip, ALL three axes satisfy: bad drift ⟹ mean < 0, which is
exactly what the one-sided mSPRT engine detects.

Because inputs are z-scored (sigma≈1 per primitive, weighted-sum-of-unit-normals),
the downstream MixtureSPRT should be constructed with sigma=1, null_mean=0.
"""
from __future__ import annotations

from research.hyperliquid.detector.config import PRIMITIVES, AXES, BAD_DIR
from research.hyperliquid.detector.shrinkage import blend


def axis_observations(prim_values: dict, baseline, cfg) -> dict[str, float]:
    """Compute per-axis signed scalar observations from raw primitive values.

    Parameters
    ----------
    prim_values : dict[str, float]
        All 9 primitive values keyed by primitive name.
    baseline : BaselineStats
        Frozen self+universe stats used for James-Stein shrinkage.
    cfg : DetectorConfig
        Configuration carrying weights and kappa.

    Returns
    -------
    dict[str, float]
        Keys == AXES.  Negative value = evidence of bad drift on that axis.
    """
    out = {}
    for axis in AXES:
        acc = 0.0
        for p in PRIMITIVES[axis]:
            mu, sigma = blend(
                baseline.self_stats[axis][p],
                baseline.universe_stats[axis][p],
                cfg.kappa,
            )
            z = (prim_values[p] - mu) / sigma
            acc += cfg.weights[axis][p] * z
        # Sign so that BAD drift maps to mean < 0 for the one-sided mSPRT:
        #   BAD_DIR[axis] > 0 → high z is bad → flip sign
        #   BAD_DIR[axis] < 0 → low z is bad → keep sign (low z already < 0)
        out[axis] = acc * (-1.0 if BAD_DIR[axis] > 0 else 1.0)
    return out
