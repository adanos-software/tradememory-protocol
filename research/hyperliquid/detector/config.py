from __future__ import annotations
from dataclasses import dataclass, field

AXES = ("exposure", "discipline", "tilt")
PRIMITIVES = {
    "exposure": ("leverage", "notional_growth", "size_in_sigma"),
    "discipline": ("stop_attach_rate", "reduce_only_rate", "mean_hold_hours"),
    "tilt": ("topup_count", "loser_add_count", "fill_rate_spike"),
}
# Direction of the BAD drift per axis. The mSPRT engine detects mean < null,
# so exposure/tilt (bad = up) get sign-flipped in axis.py; discipline (bad = down) does not.
BAD_DIR = {"exposure": +1, "discipline": -1, "tilt": +1}

@dataclass(frozen=True)
class PrimitiveStats:
    mean: float
    std: float
    n: int

@dataclass
class BaselineStats:
    # self[axis][primitive] = PrimitiveStats from the master's pre-T0 history
    self_stats: dict
    # universe[axis][primitive] = PrimitiveStats from the tuning-split cross-section
    universe_stats: dict

@dataclass(frozen=True)
class DetectorConfig:
    bucket_ms: int
    M: int
    tau: dict            # per-axis mixing scale
    weights: dict        # weights[axis][primitive], sum |w| = 1 per axis
    kappa: float         # James-Stein shrinkage strength (buckets/obs)
    burn_in: int = 20
    alpha: float = 0.01            # per-axis, pre-reg #12
    guard_x: float = 0.70          # pre-reg #14
    @property
    def holm_gate(self) -> float:
        return self.alpha / 3.0
