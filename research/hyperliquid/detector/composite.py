"""Holm-min-gate + sustained-M composite alert.

Fires when the minimum p-value across axes falls at or below the Holm-corrected
gate (alpha / |AXES|) for M consecutive buckets.  Raises alert_raised exactly
once (latches on first trigger).

Design:
- "fired" this bucket  <=>  min(p_by_axis) <= cfg.holm_gate
- counter increments on fire, resets to 0 on miss
- alert_raised True at the first bucket where counter >= M  (latches)
- carrying_axis = argmin axis (only set when fired)
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CompositeStep:
    fired: bool
    alert_raised: bool
    carrying_axis: str | None


class Composite:
    """Stateful composite alert tracker.

    Parameters
    ----------
    cfg : DetectorConfig
        Provides holm_gate (= alpha / len(AXES)) and M.
    """

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.counter = 0
        self.latched = False

    def step(self, p_by_axis: dict[str, float]) -> CompositeStep:
        """Advance by one bucket.

        Parameters
        ----------
        p_by_axis : dict[str, float]
            p-values keyed by axis name (all three axes expected).

        Returns
        -------
        CompositeStep
            fired       — this bucket exceeded the gate
            alert_raised — first bucket where sustained counter reached M
            carrying_axis — argmin axis when fired, else None
        """
        carrying = min(p_by_axis, key=p_by_axis.get)
        fired = p_by_axis[carrying] <= self.cfg.holm_gate

        self.counter = self.counter + 1 if fired else 0

        alert = False
        if not self.latched and fired and self.counter >= self.cfg.M:
            alert = True
            self.latched = True

        return CompositeStep(
            fired=fired,
            alert_raised=alert,
            carrying_axis=carrying if fired else None,
        )
