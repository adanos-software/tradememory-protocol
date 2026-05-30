"""Per-axis mSPRT wrapper.

Thin wrapper around the MC-validated MixtureSPRT engine: one instance per axis,
constructed with sigma=1 and null_mean=0 (matching the z-scored signed
observations produced by axis_observations() in axis.py).

Intentional design:
- No burn_in masking: MixtureSPRT.p_value is always-valid even during burn_in.
  The burn_in flag only gates the engine's own RETIRE decision; p_value is
  real and monotonically useful from observation 1.  The composite layer
  (next phase) has no separate burn_in gate — calibration absorbs it.
- No engine reimplementation: full reuse of tradememory.ssrt.core.MixtureSPRT.
"""
from __future__ import annotations

from tradememory.ssrt.core import MixtureSPRT
from research.hyperliquid.detector.config import AXES


class AxisSPRT:
    """One MixtureSPRT per axis; state is independent across axes.

    Parameters
    ----------
    cfg : DetectorConfig
        Provides alpha, tau (per-axis), and burn_in.
    """

    def __init__(self, cfg) -> None:
        self._sprt: dict[str, MixtureSPRT] = {
            axis: MixtureSPRT(
                alpha=cfg.alpha,
                tau=cfg.tau[axis],
                sigma=1.0,      # observations are z-scored (unit variance)
                null_mean=0.0,  # bad drift → mean below 0 (after sign flip)
                burn_in=cfg.burn_in,
            )
            for axis in AXES
        }

    def update(self, axis: str, signed_obs: float) -> float:
        """Feed one signed observation to the given axis engine.

        Parameters
        ----------
        axis : str
            One of AXES ("exposure", "discipline", "tilt").
        signed_obs : float
            Signed scalar from axis_observations(); negative = bad drift evidence.

        Returns
        -------
        float
            Always-valid p-value in (0, 1].  Lower = stronger evidence of drift.
        """
        return self._sprt[axis].update(signed_obs).p_value
