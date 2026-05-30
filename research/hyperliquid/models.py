from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Trade:
    time: int            # UTC epoch ms
    coin: str
    direction: str       # raw `dir`
    px: float
    sz: float
    closed_pnl: float
    start_position: float
    is_liquidation: bool


@dataclass(frozen=True)
class EquityPoint:
    time: int
    value: float


@dataclass(frozen=True)
class LedgerEvent:
    time: int
    type: str
    usdc: float


@dataclass
class Trajectory:
    address: str
    trades: list
    equity: list
    ledger: list
    stop_order_rate: float
    first_trade_ms: int
    last_trade_ms: int


@dataclass
class CohortMember:
    address: str
    label: str                      # "blowup" | "stable"
    blowup_time: int | None
    event_cluster: str | None       # YYYY-MM-DD (UTC) of blow-up
    baseline_trades: int
    baseline_days: float


@dataclass
class CohortManifest:
    t0_ms: int
    window_end_ms: int
    members: list = field(default_factory=list)
    excluded_short_baseline: int = 0
    excluded_no_data: int = 0

    @property
    def blowups(self):
        return [m for m in self.members if m.label == "blowup"]

    @property
    def stable(self):
        return [m for m in self.members if m.label == "stable"]

    @property
    def base_rate(self):
        return len(self.blowups) / len(self.members) if self.members else 0.0

    @property
    def effective_n_events(self):
        return len({m.event_cluster for m in self.blowups if m.event_cluster})
