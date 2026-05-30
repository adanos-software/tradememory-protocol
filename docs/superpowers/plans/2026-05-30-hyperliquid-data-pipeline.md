# Hyperliquid Data Pipeline (Plan 1 of 3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested, isolated package that turns the Hyperliquid public API into per-trader behavioral trajectories and a frozen-at-T₀ cohort with forward-only blow-up labels, archiving every raw response — the data foundation for the copy-trading drift paper.

**Architecture:** Standalone package `research/hyperliquid/` that does NOT touch `src/tradememory/`. Network I/O is isolated behind an injectable transport so all logic is unit-tested offline. Normalization and the blow-up labeler are pure functions (no network, no hidden state). A CLI enumerates a frozen universe and emits a cohort manifest + a go/no-go decision report. Forward-only / no-look-ahead is a first-class correctness property, tested explicitly.

**Tech Stack:** Python 3.10+, stdlib `urllib` (no new runtime dep), `pytest` + `hypothesis` (already in repo). Isolated test run: `python -m pytest research/hyperliquid/tests/ -v` (kept OUT of the main 1374-test suite so research WIP never breaks the gate).

**Spec:** `docs/superpowers/specs/2026-05-30-copytrading-drift-paper-design.md` (§5.3 guard band, §5.4 forward-only T, §6 frozen universe, §11 archiving). **Build constraints:** branch `copytrading-drift-demo`; never edit `src/tradememory/mcp_server.py`; UTC everywhere; secrets via env only.

**Out of scope (→ Plan 2):** behavioral axis features, the detector, synthetic MC calibration. Plan 1 stops at clean trajectories + labels + cohort manifest.

---

## File Structure

| File | Responsibility |
|---|---|
| `research/hyperliquid/__init__.py` | package marker |
| `research/hyperliquid/models.py` | dataclasses: `Trade`, `EquityPoint`, `LedgerEvent`, `Trajectory`, `CohortMember`, `CohortManifest` |
| `research/hyperliquid/client.py` | `HyperliquidClient` — injectable transport, POST `/info`, paginate `userFillsByTime`, fetch portfolio/orders/ledger, archive raw JSON + query timestamp |
| `research/hyperliquid/normalize.py` | pure: `normalize_fills`, `equity_curve`, `drawdown_series`, `ledger_events`, `stop_order_rate` |
| `research/hyperliquid/blowup.py` | pure: `forward_only_blowup_time` (§5.4) — the paper-critical correctness unit |
| `research/hyperliquid/trajectory.py` | `build_trajectory` (assemble), `meets_baseline` (min pre-event history inclusion) |
| `research/hyperliquid/universe.py` | `load_universe_snapshot`, `label_cohort` (forward labeling, base rate, exclusion counts, liquidation-day event clusters) |
| `research/hyperliquid/__main__.py` | CLI: enumerate universe → cohort manifest + `COHORT-REPORT.md` |
| `research/hyperliquid/tests/conftest.py` | fixtures: small real-shaped raw responses + a `FakeTransport` |
| `research/hyperliquid/tests/test_*.py` | one test module per source module |

All timestamps are UTC epoch-ms (Hyperliquid native). Money/size kept as `float` (sufficient for behavioral stats; document the precision choice).

---

## Task 1: Scaffold package + fixtures + FakeTransport

**Files:**
- Create: `research/hyperliquid/__init__.py` (empty)
- Create: `research/hyperliquid/tests/__init__.py` (empty)
- Create: `research/hyperliquid/tests/conftest.py`
- Test: `research/hyperliquid/tests/test_smoke.py`

- [ ] **Step 1: Write conftest fixtures (real-shaped, from the 2026-05-30 spike)**

```python
# research/hyperliquid/tests/conftest.py
import pytest

@pytest.fixture
def raw_fills():
    # shape verified against live API 2026-05-30; one normal close + one liquidation fill
    return [
        {"time": 1749513600000, "coin": "kPEPE", "dir": "Close Long", "px": "0.010491",
         "sz": "367453.0", "closedPnl": "-690.81", "startPosition": "367453.0",
         "side": "A", "crossed": True, "fee": "1.2", "tid": 1, "hash": "0xa"},
        {"time": 1749513660000, "coin": "BTC", "dir": "Close Long", "px": "60000.0",
         "sz": "2.0", "closedPnl": "-50000.0", "startPosition": "2.0", "side": "A",
         "crossed": True, "fee": "5.0", "tid": 2, "hash": "0xb",
         "liquidation": {"liquidatedUser": "0xabc", "markPx": "60000.0", "method": "market"}},
    ]

@pytest.fixture
def raw_portfolio():
    # [periodName, {accountValueHistory: [[ts, "val"], ...], pnlHistory, vlm}]
    return [
        ["perpAllTime", {
            "accountValueHistory": [
                [1749000000000, "1000000.0"], [1749500000000, "1895650.0"],
                [1749520000000, "500000.0"], [1749600000000, "0.0"],
            ],
            "pnlHistory": [[1749000000000, "0.0"]], "vlm": "0.0"}],
    ]

@pytest.fixture
def raw_ledger():
    return [
        {"time": 1749499620000, "delta": {"type": "deposit", "usdc": "19942.95"}},
        {"time": 1749499700000, "delta": {"type": "deposit", "usdc": "33205.43"}},
        {"time": 1749600000000, "delta": {"type": "withdraw", "usdc": "1000.0"}},
    ]

@pytest.fixture
def raw_orders():
    return [
        {"coin": "BTC", "side": "B", "limitPx": "60000", "sz": "1", "oid": 1,
         "timestamp": 1749000000000, "isTrigger": False, "isPositionTpsl": False,
         "reduceOnly": False, "orderType": "Limit", "triggerPx": "0", "status": "filled"},
        {"coin": "BTC", "side": "A", "limitPx": "0", "sz": "1", "oid": 2,
         "timestamp": 1749000100000, "isTrigger": True, "isPositionTpsl": True,
         "reduceOnly": True, "orderType": "Stop Market", "triggerPx": "58000", "status": "open"},
    ]

class FakeTransport:
    """Injectable stand-in for the network. Records calls; returns queued responses,
    or delegates to a side_effect callable (for stateful pagination tests).
    NOTE: dispatch lives in __call__ on the CLASS — never monkeypatch ft.__call__ on an
    instance (Python looks up dunders on the type, so an instance attr is ignored)."""
    def __init__(self, responses=None, side_effect=None):
        self._responses = list(responses or [])   # list of (predicate(body)->bool, response)
        self._side_effect = side_effect            # callable(body)->response, takes priority
        self.calls = []
    def __call__(self, body):
        self.calls.append(body)
        if self._side_effect is not None:
            return self._side_effect(body)
        for pred, resp in self._responses:
            if pred(body):
                return resp
        raise AssertionError(f"no fake response for body={body}")

@pytest.fixture
def fake_transport_cls():
    return FakeTransport
```

- [ ] **Step 2: Write the smoke test**

```python
# research/hyperliquid/tests/test_smoke.py
def test_package_imports():
    import research.hyperliquid  # noqa: F401

def test_fixtures_load(raw_fills, raw_portfolio, raw_ledger, raw_orders):
    assert raw_fills[1]["liquidation"]["method"] == "market"
    assert raw_portfolio[0][0] == "perpAllTime"
```

- [ ] **Step 3: Create the two empty `__init__.py` files + gitignore the archive dir**

Create `research/hyperliquid/__init__.py` and `research/hyperliquid/tests/__init__.py` (empty).
Run: `python -c "import os; [open(p,'w').close() for p in ['research/hyperliquid/__init__.py','research/hyperliquid/tests/__init__.py']]"`
Then append `research/hyperliquid/_archive/` to the repo-root `.gitignore` (large raw API JSON must never be staged — the client writes there by default).
**Import note:** run pytest from the repo root (`python -m pytest research/hyperliquid/tests/ -v`); `research/` resolves as a PEP 420 namespace package so `import research.hyperliquid` works without a `research/__init__.py`. Running pytest from inside `research/hyperliquid/` will fail with `ModuleNotFoundError: research`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest research/hyperliquid/tests/test_smoke.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add research/hyperliquid/
git commit -m "feat(hl): scaffold hyperliquid data-pipeline package + test fixtures"
```

---

## Task 2: Data models

**Files:**
- Create: `research/hyperliquid/models.py`
- Test: `research/hyperliquid/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# research/hyperliquid/tests/test_models.py
from research.hyperliquid.models import Trade, EquityPoint, Trajectory

def test_trade_is_liquidation_flag():
    t = Trade(time=1, coin="BTC", direction="Close Long", px=1.0, sz=1.0,
              closed_pnl=-5.0, start_position=1.0, is_liquidation=True)
    assert t.is_liquidation

def test_trajectory_holds_components():
    traj = Trajectory(address="0xabc", trades=[], equity=[EquityPoint(1, 100.0)],
                      ledger=[], stop_order_rate=0.5, first_trade_ms=1, last_trade_ms=1)
    assert traj.address == "0xabc"
    assert traj.equity[0].value == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest research/hyperliquid/tests/test_models.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement models**

```python
# research/hyperliquid/models.py
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
    type: str            # deposit | withdraw | ...
    usdc: float

@dataclass
class Trajectory:
    address: str
    trades: list[Trade]
    equity: list[EquityPoint]
    ledger: list[LedgerEvent]
    stop_order_rate: float          # fraction of orders that were stop/trigger
    first_trade_ms: int
    last_trade_ms: int

@dataclass
class CohortMember:
    address: str
    label: str                      # "blowup" | "stable"
    blowup_time: int | None
    event_cluster: str | None       # YYYY-MM-DD (UTC) of blow-up, for clustering
    baseline_trades: int
    baseline_days: float

@dataclass
class CohortManifest:
    t0_ms: int
    window_end_ms: int
    members: list[CohortMember] = field(default_factory=list)
    excluded_short_baseline: int = 0
    excluded_no_data: int = 0
    @property
    def blowups(self): return [m for m in self.members if m.label == "blowup"]
    @property
    def stable(self): return [m for m in self.members if m.label == "stable"]
    @property
    def base_rate(self):
        return len(self.blowups) / len(self.members) if self.members else 0.0
    @property
    def effective_n_events(self):
        return len({m.event_cluster for m in self.blowups if m.event_cluster})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest research/hyperliquid/tests/test_models.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add research/hyperliquid/models.py research/hyperliquid/tests/test_models.py
git commit -m "feat(hl): data models (Trade/Equity/Trajectory/Cohort)"
```

---

## Task 3: API client + raw-response archive (injectable transport)

**Files:**
- Create: `research/hyperliquid/client.py`
- Test: `research/hyperliquid/tests/test_client.py`

- [ ] **Step 1: Write the failing test (no real network — FakeTransport)**

```python
# research/hyperliquid/tests/test_client.py
import json
from pathlib import Path
from research.hyperliquid.client import HyperliquidClient

def test_post_archives_raw_response(tmp_path, fake_transport_cls):
    ft = fake_transport_cls([(lambda b: b["type"] == "portfolio", {"ok": 1})])
    c = HyperliquidClient(transport=ft, archive_dir=tmp_path)
    out = c.post({"type": "portfolio", "user": "0xabc"})
    assert out == {"ok": 1}
    files = list(Path(tmp_path).rglob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text())
    assert saved["request"]["type"] == "portfolio"
    assert saved["response"] == {"ok": 1}
    assert "query_time_ms" in saved   # reproducibility per spec §11

def test_fetch_user_fills_paginates_and_dedupes(tmp_path, fake_transport_cls):
    page1 = [{"tid": i, "time": 1000 + i} for i in range(2000)]              # tids 0..1999
    # page2 = one duplicate (tid 1999) + five genuinely-new (tids 2000..2004)
    page2 = [{"tid": 1999, "time": 2999}] + [{"tid": i, "time": 3000 + i} for i in range(2000, 2005)]
    def resp(body):
        return page1 if body["startTime"] <= 1000 else page2
    ft = fake_transport_cls(side_effect=resp)        # proper hook, NOT a dunder monkeypatch
    c = HyperliquidClient(transport=ft, archive_dir=tmp_path)
    fills = c.fetch_user_fills_by_time("0xabc", start_ms=1000, max_pages=3)
    tids = [f["tid"] for f in fills]
    assert len(tids) == len(set(tids))            # deduped
    assert tids.count(1999) == 1                   # duplicate kept exactly once
    assert len(fills) == 2005                       # 2000 + 5 genuinely new (1999 dropped)
    assert c.last_fetch_truncated is False          # stopped on a short page, not the page cap
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest research/hyperliquid/tests/test_client.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement client**

```python
# research/hyperliquid/client.py
from __future__ import annotations
import json, time, urllib.request
from pathlib import Path
from typing import Callable

API = "https://api.hyperliquid.xyz/info"

def _default_transport(body: dict) -> object:
    req = urllib.request.Request(
        API, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "tm-research/0.1"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())

class HyperliquidClient:
    def __init__(self, transport: Callable[[dict], object] | None = None,
                 archive_dir: str | Path = "research/hyperliquid/_archive",
                 rate_delay_s: float = 0.3, clock=lambda: int(time.time() * 1000)):
        self._transport = transport or _default_transport
        self._archive = Path(archive_dir)
        self._rate_delay_s = rate_delay_s
        self._clock = clock
        self._archive_seq = 0
        self.last_fetch_truncated = False   # set by fetch_user_fills_by_time (10k-cap proxy)

    def post(self, body: dict) -> object:
        resp = self._transport(body)
        self._archive_raw(body, resp)
        return resp

    def _archive_raw(self, body: dict, resp: object) -> None:
        user = body.get("user", "global")
        d = self._archive / user
        d.mkdir(parents=True, exist_ok=True)
        ts = self._clock()
        self._archive_seq += 1   # avoid same-ms overwrite during pagination
        path = d / f"{body['type']}_{ts}_{self._archive_seq}.json"
        path.write_text(json.dumps(
            {"query_time_ms": ts, "request": body, "response": resp}))

    def fetch_user_fills_by_time(self, user: str, start_ms: int,
                                 end_ms: int | None = None, max_pages: int = 6) -> list[dict]:
        """Paginate userFillsByTime (<=2000/page, <=10k available). Dedupe by tid.
        Sets self.last_fetch_truncated=True iff the page cap was hit with a still-full
        last page (i.e. more history exists than we fetched — the 10k-cap selection-bias proxy)."""
        seen, out, cur = set(), [], start_ms
        self.last_fetch_truncated = False
        for i in range(max_pages):
            body = {"type": "userFillsByTime", "user": user,
                    "startTime": cur, "aggregateByTime": False}
            if end_ms is not None:
                body["endTime"] = end_ms
            batch = self.post(body)
            if not batch:
                break
            new = [f for f in batch if f["tid"] not in seen]
            for f in new:
                seen.add(f["tid"])
            out.extend(new)
            if len(batch) < 2000:
                break
            if i == max_pages - 1:
                self.last_fetch_truncated = True   # full last page at the cap => truncated
            cur = max(f["time"] for f in batch) + 1
            time.sleep(self._rate_delay_s)
        return out

    def fetch_portfolio(self, user: str) -> object:
        return self.post({"type": "portfolio", "user": user})
    def fetch_historical_orders(self, user: str) -> object:
        return self.post({"type": "historicalOrders", "user": user})
    def fetch_ledger(self, user: str, start_ms: int) -> object:
        return self.post({"type": "userNonFundingLedgerUpdates",
                          "user": user, "startTime": start_ms})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest research/hyperliquid/tests/test_client.py -v`
Expected: 2 passed. (If the pagination monkeypatch in the test is awkward, simplify `FakeTransport` to take a `side_effect` callable — keep the dedupe+stop-on-short-page assertions.)

- [ ] **Step 5: Commit**

```bash
git add research/hyperliquid/client.py research/hyperliquid/tests/test_client.py
git commit -m "feat(hl): API client with pagination + raw-response archive"
```

---

## Task 4: Normalizers (fills, equity, drawdown, ledger, stop-rate)

**Files:**
- Create: `research/hyperliquid/normalize.py`
- Test: `research/hyperliquid/tests/test_normalize.py`

- [ ] **Step 1: Write the failing tests**

```python
# research/hyperliquid/tests/test_normalize.py
from research.hyperliquid.normalize import (
    normalize_fills, equity_curve, drawdown_series, ledger_events, stop_order_rate)

def test_normalize_marks_liquidation(raw_fills):
    trades = normalize_fills(raw_fills)
    assert len(trades) == 2
    assert trades[0].is_liquidation is False
    assert trades[1].is_liquidation is True          # has `liquidation` key
    assert trades[0].closed_pnl == -690.81

def test_equity_curve_parses_and_sorts(raw_portfolio):
    eq = equity_curve(raw_portfolio, period="perpAllTime")
    assert [p.value for p in eq] == [1000000.0, 1895650.0, 500000.0, 0.0]
    assert eq == sorted(eq, key=lambda p: p.time)

def test_drawdown_from_running_peak(raw_portfolio):
    eq = equity_curve(raw_portfolio, period="perpAllTime")
    dd = drawdown_series(eq)               # fraction below running peak
    assert dd[1] == 0.0                     # new peak
    assert abs(dd[3] - 1.0) < 1e-9          # 1895650 -> 0 == 100% drawdown

def test_stop_order_rate(raw_orders):
    assert stop_order_rate(raw_orders) == 0.5   # 1 of 2 is trigger/stop

def test_ledger_events_typed(raw_ledger):
    evs = ledger_events(raw_ledger)
    assert [e.type for e in evs] == ["deposit", "deposit", "withdraw"]
    assert evs[0].usdc == 19942.95
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest research/hyperliquid/tests/test_normalize.py -v` → FAIL.

- [ ] **Step 3: Implement normalize.py**

```python
# research/hyperliquid/normalize.py
from __future__ import annotations
from research.hyperliquid.models import Trade, EquityPoint, LedgerEvent

def normalize_fills(raw: list[dict]) -> list[Trade]:
    out = []
    for f in raw:
        out.append(Trade(
            time=int(f["time"]), coin=f["coin"], direction=f.get("dir", ""),
            px=float(f["px"]), sz=float(f["sz"]),
            closed_pnl=float(f.get("closedPnl", 0.0)),
            start_position=float(f.get("startPosition", 0.0)),
            is_liquidation=("liquidation" in f)))   # spike-verified marker
    return sorted(out, key=lambda t: t.time)

def equity_curve(raw_portfolio: list, period: str = "perpAllTime") -> list[EquityPoint]:
    by_period = {p[0]: p[1] for p in raw_portfolio}
    avh = by_period.get(period, {}).get("accountValueHistory", [])
    pts = [EquityPoint(int(t), float(v)) for t, v in avh]
    return sorted(pts, key=lambda p: p.time)

def drawdown_series(eq: list[EquityPoint]) -> list[float]:
    out, peak = [], float("-inf")
    for p in eq:
        peak = max(peak, p.value)
        out.append(0.0 if peak <= 0 else (peak - p.value) / peak)
    return out

def ledger_events(raw: list[dict]) -> list[LedgerEvent]:
    out = []
    for u in raw:
        d = u["delta"]
        amt = d.get("usdc", d.get("amount", 0.0))
        out.append(LedgerEvent(int(u["time"]), d["type"], float(amt)))
    return sorted(out, key=lambda e: e.time)

def stop_order_rate(raw_orders: list[dict]) -> float:
    if not raw_orders:
        return 0.0
    n_stop = sum(1 for o in raw_orders
                 if o.get("isTrigger") or o.get("isPositionTpsl"))   # flat shape (spike-verified)
    return n_stop / len(raw_orders)
```

- [ ] **Step 4: Run to verify pass** → `python -m pytest research/hyperliquid/tests/test_normalize.py -v` → 5 passed.

- [ ] **Step 5: Commit**

```bash
git add research/hyperliquid/normalize.py research/hyperliquid/tests/test_normalize.py
git commit -m "feat(hl): normalizers (fills/equity/drawdown/ledger/stop-rate)"
```

---

## Task 5: Forward-only blow-up labeler (PAPER-CRITICAL — §5.4)

The single most correctness-sensitive unit. T = the earlier of (a) first time cumulative drawdown from running peak exceeds `dd_pct` **and** equity does not recover above the `recovery_frac × peak` within `recovery_horizon_ms`, or (b) first liquidation fill. **No bar after the candidate+horizon may influence whether T is emitted** — tested explicitly.

**Files:**
- Create: `research/hyperliquid/blowup.py`
- Test: `research/hyperliquid/tests/test_blowup.py`

- [ ] **Step 1: Write the failing tests (clean / recovery / liquidation-first / no-look-ahead)**

```python
# research/hyperliquid/tests/test_blowup.py
from research.hyperliquid.models import EquityPoint, Trade
from research.hyperliquid.blowup import forward_only_blowup_time

H = 86_400_000  # 1 day in ms

def eq(seq):  # helper: list of (t_days, value)
    return [EquityPoint(int(t * H), float(v)) for t, v in seq]

def test_clean_blowup_labels_at_threshold_cross():
    curve = eq([(0, 100), (1, 120), (2, 55), (3, 0)])   # peak 120; t=2 dd=54% (> 50%)
    t = forward_only_blowup_time(curve, [], dd_pct=0.5,
                                 recovery_frac=0.8, recovery_horizon_ms=H)
    assert t == int(2 * H)        # first bar with dd>50% that never recovers

def test_transient_dip_with_recovery_is_not_a_blowup():
    curve = eq([(0, 100), (1, 50), (2, 95), (3, 110)])  # dips 50% then recovers
    t = forward_only_blowup_time(curve, [], dd_pct=0.5,
                                 recovery_frac=0.8, recovery_horizon_ms=2 * H)
    assert t is None

def test_liquidation_fill_takes_precedence_if_earlier():
    curve = eq([(0, 100), (5, 80)])
    liq = [Trade(time=int(1 * H), coin="BTC", direction="Close Long", px=1, sz=1,
                 closed_pnl=-99, start_position=1, is_liquidation=True)]
    t = forward_only_blowup_time(curve, liq, dd_pct=0.5,
                                 recovery_frac=0.8, recovery_horizon_ms=H)
    assert t == int(1 * H)

def test_no_look_ahead_truncating_future_does_not_change_label():
    # The label at/after the candidate must depend only on data within [candidate, candidate+horizon].
    base = eq([(0, 100), (1, 120), (2, 55)])   # t=2 dd=54% (> 50%)
    future_a = base + eq([(3, 0)])
    future_b = base + eq([(3, 0), (10, 999999)])  # wild future spike beyond horizon
    t_a = forward_only_blowup_time(future_a, [], 0.5, 0.8, H)
    t_b = forward_only_blowup_time(future_b, [], 0.5, 0.8, H)
    assert t_a == t_b == int(2 * H)   # future beyond horizon must not matter

def test_recovery_within_horizon_blocks_label_but_outside_does_not():
    # candidate at t=2 (dd>50% of peak 120). A recovery to >=0.8*peak WITHIN the horizon
    # cancels the blow-up; the SAME recovery placed BEYOND the horizon does not.
    within = eq([(0, 100), (1, 120), (2, 55), (2.5, 100)])   # recover +0.5d (<= H)
    beyond = eq([(0, 100), (1, 120), (2, 55), (4, 100)])     # recover +2d  (>  H)
    assert forward_only_blowup_time(within, [], 0.5, 0.8, H) is None
    assert forward_only_blowup_time(beyond, [], 0.5, 0.8, H) == int(2 * H)
```

- [ ] **Step 2: Run to verify fail** → FAIL.

- [ ] **Step 3: Implement blowup.py**

```python
# research/hyperliquid/blowup.py
from __future__ import annotations
from research.hyperliquid.models import EquityPoint, Trade

def forward_only_blowup_time(
    equity: list[EquityPoint], trades: list[Trade],
    dd_pct: float, recovery_frac: float, recovery_horizon_ms: int,
    initial_peak: float = float("-inf")) -> int | None:
    """Earliest blow-up time T using ONLY data within [candidate, candidate+horizon].
    (a) first equity bar whose drawdown-from-running-peak > dd_pct AND which does not
        recover above recovery_frac*peak within recovery_horizon_ms; or
    (b) first liquidation fill — whichever is earlier.
    `initial_peak` seeds the running peak with the genuine (e.g. pre-T0) peak so drawdown
    is measured against true history, not just the sliced window (see label_cohort)."""
    liq_t = next((t.time for t in sorted(trades, key=lambda x: x.time)
                  if t.is_liquidation), None)

    eq = sorted(equity, key=lambda p: p.time)
    dd_t = None
    peak = initial_peak
    for i, p in enumerate(eq):
        peak = max(peak, p.value)
        if peak <= 0:
            continue
        dd = (peak - p.value) / peak
        if dd > dd_pct:
            # forward-only recovery check, bounded to the horizon window
            recovered = False
            for q in eq[i:]:
                if q.time - p.time > recovery_horizon_ms:
                    break
                if q.value >= recovery_frac * peak:
                    recovered = True
                    break
            if not recovered:
                dd_t = p.time
                break

    candidates = [t for t in (liq_t, dd_t) if t is not None]
    return min(candidates) if candidates else None
```

- [ ] **Step 4: Run to verify pass** → `python -m pytest research/hyperliquid/tests/test_blowup.py -v` → 4 passed.

- [ ] **Step 5: Commit**

```bash
git add research/hyperliquid/blowup.py research/hyperliquid/tests/test_blowup.py
git commit -m "feat(hl): forward-only blow-up labeler (no look-ahead, tested)"
```

---

## Task 6: Trajectory assembly + min-baseline inclusion

**Files:**
- Create: `research/hyperliquid/trajectory.py`
- Test: `research/hyperliquid/tests/test_trajectory.py`

- [ ] **Step 1: Write the failing tests**

```python
# research/hyperliquid/tests/test_trajectory.py
from research.hyperliquid.trajectory import build_trajectory, meets_baseline

def test_build_trajectory_from_raw(raw_fills, raw_portfolio, raw_ledger, raw_orders):
    traj = build_trajectory("0xabc", raw_fills, raw_portfolio, raw_ledger, raw_orders)
    assert traj.address == "0xabc"
    assert len(traj.trades) == 2
    assert traj.stop_order_rate == 0.5
    assert traj.first_trade_ms == 1749513600000

def test_meets_baseline_requires_min_history_before_t(raw_fills, raw_portfolio, raw_ledger, raw_orders):
    traj = build_trajectory("0xabc", raw_fills, raw_portfolio, raw_ledger, raw_orders)
    # event at far future: enough pre-event history
    assert meets_baseline(traj, t_event_ms=1749513600000 + 10**9,
                          min_trades=2, min_days=0.0) is True
    # event before any trades: no baseline
    assert meets_baseline(traj, t_event_ms=1, min_trades=2, min_days=0.0) is False
```

- [ ] **Step 2: Run to verify fail** → FAIL.

- [ ] **Step 3: Implement trajectory.py**

```python
# research/hyperliquid/trajectory.py
from __future__ import annotations
from research.hyperliquid.models import Trajectory
from research.hyperliquid.normalize import (
    normalize_fills, equity_curve, ledger_events, stop_order_rate)

def build_trajectory(address, raw_fills, raw_portfolio, raw_ledger, raw_orders,
                     period="perpAllTime") -> Trajectory:
    trades = normalize_fills(raw_fills)
    eq = equity_curve(raw_portfolio, period=period)
    led = ledger_events(raw_ledger)
    rate = stop_order_rate(raw_orders)
    first = trades[0].time if trades else 0
    last = trades[-1].time if trades else 0
    return Trajectory(address=address, trades=trades, equity=eq, ledger=led,
                      stop_order_rate=rate, first_trade_ms=first, last_trade_ms=last)

def meets_baseline(traj: Trajectory, t_event_ms: int,
                   min_trades: int, min_days: float) -> bool:
    """Spec §6 item 4: require enough pre-event history so the detector has a baseline."""
    pre = [t for t in traj.trades if t.time < t_event_ms]
    if len(pre) < min_trades:
        return False
    if not pre:
        return False
    span_days = (t_event_ms - pre[0].time) / 86_400_000
    return span_days >= min_days
```

- [ ] **Step 4: Run to verify pass** → 2 passed.

- [ ] **Step 5: Commit**

```bash
git add research/hyperliquid/trajectory.py research/hyperliquid/tests/test_trajectory.py
git commit -m "feat(hl): trajectory assembly + min-baseline inclusion rule"
```

---

## Task 7: Frozen-universe cohort labeling (§6 — kills survivorship bias)

Input = a frozen list of addresses that were active at/before T₀ (assembled offline from multiple sources — see Task 8 note). Labeling rolls forward from T₀ using only post-T₀ data; blow-up/stable is determined by the FUTURE, never by a survival filter. Emits base rate, event clusters (liquidation-day), and exclusion counts as named lines.

**Files:**
- Create: `research/hyperliquid/universe.py`
- Test: `research/hyperliquid/tests/test_universe.py`

- [ ] **Step 1: Write the failing tests**

```python
# research/hyperliquid/tests/test_universe.py
from datetime import datetime, timezone
from research.hyperliquid.models import Trajectory, EquityPoint, Trade
from research.hyperliquid.universe import label_cohort

H = 86_400_000
def _traj(addr, eq, trades):
    return Trajectory(addr, trades, [EquityPoint(int(t*H), float(v)) for t, v in eq],
                      [], 1.0, trades[0].time if trades else 0,
                      trades[-1].time if trades else 0)

def test_label_cohort_future_determines_outcome():
    t0 = int(10 * H)
    # A blows up after T0; B stays solvent -> stable (NOT a selection filter)
    a = _traj("0xa", [(0, 100), (11, 120), (12, 0)],
              [Trade(int(5*H), "BTC", "Open Long", 1, 1, 0, 0, False),
               Trade(int(6*H), "BTC", "Open Long", 1, 1, 0, 0, False)])
    b = _traj("0xb", [(0, 100), (20, 130)],
              [Trade(int(5*H), "BTC", "Open Long", 1, 1, 0, 0, False),
               Trade(int(6*H), "BTC", "Open Long", 1, 1, 0, 0, False)])
    man = label_cohort([a, b], t0_ms=t0, window_end_ms=int(30*H),
                       dd_pct=0.5, recovery_frac=0.8, recovery_horizon_ms=H,
                       min_trades=2, min_days=0.0)
    labels = {m.address: m.label for m in man.members}
    assert labels == {"0xa": "blowup", "0xb": "stable"}
    assert man.base_rate == 0.5
    assert man.blowups[0].event_cluster == datetime.fromtimestamp(
        man.blowups[0].blowup_time/1000, tz=timezone.utc).strftime("%Y-%m-%d")

def test_short_baseline_excluded_and_counted():
    t0 = int(10 * H)
    c = _traj("0xc", [(0, 100), (11, 0)], [Trade(int(9*H), "BTC", "Open Long", 1,1,0,0,False)])
    man = label_cohort([c], t0_ms=t0, window_end_ms=int(30*H),
                       dd_pct=0.5, recovery_frac=0.8, recovery_horizon_ms=H,
                       min_trades=5, min_days=0.0)
    assert man.members == []
    assert man.excluded_short_baseline == 1

def test_high_pre_t0_peak_crater_is_blowup():
    # Regression for the peak-reset hindsight bug: pre-T0 peak 200, post-T0 falls to 90
    # = 55% drawdown from the GENUINE peak. Must label blowup (not 'stable' from a sliced peak).
    t0 = int(10 * H)
    trades = [Trade(int(d*H), "BTC", "Open Long", 1, 1, 0, 0, False) for d in (1, 2, 3)]
    a = _traj("0xa", [(1, 150), (5, 200), (11, 90), (12, 85)], trades)
    man = label_cohort([a], t0_ms=t0, window_end_ms=int(30*H),
                       dd_pct=0.5, recovery_frac=0.8, recovery_horizon_ms=H,
                       min_trades=3, min_days=0.0)
    assert [m.label for m in man.members] == ["blowup"]

def test_effective_n_events_clusters_by_utc_day():
    t0 = int(10 * H)
    def blow(addr, blow_day):
        trs = [Trade(int(d*H), "BTC", "Open Long", 1, 1, 0, 0, False) for d in (1, 2)]
        return _traj(addr, [(1, 100), (blow_day, 0)], trs)
    same1, same2 = blow("0x1", 11), blow("0x2", 11)   # both blow on day 11
    man = label_cohort([same1, same2], t0_ms=t0, window_end_ms=int(30*H),
                       dd_pct=0.5, recovery_frac=0.8, recovery_horizon_ms=H,
                       min_trades=2, min_days=0.0)
    assert len(man.blowups) == 2
    assert man.effective_n_events == 1                 # same UTC day -> ONE event cluster
    man2 = label_cohort([same1, blow("0x3", 20)], t0_ms=t0, window_end_ms=int(30*H),
                        dd_pct=0.5, recovery_frac=0.8, recovery_horizon_ms=H,
                        min_trades=2, min_days=0.0)
    assert man2.effective_n_events == 2                # different UTC days -> two events
```

- [ ] **Step 2: Run to verify fail** → FAIL.

- [ ] **Step 3: Implement universe.py**

```python
# research/hyperliquid/universe.py
from __future__ import annotations
from datetime import datetime, timezone
from research.hyperliquid.models import Trajectory, CohortMember, CohortManifest
from research.hyperliquid.blowup import forward_only_blowup_time
from research.hyperliquid.trajectory import meets_baseline

def _utc_day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

def label_cohort(trajectories: list[Trajectory], t0_ms: int, window_end_ms: int,
                 dd_pct: float, recovery_frac: float, recovery_horizon_ms: int,
                 min_trades: int, min_days: float) -> CohortManifest:
    man = CohortManifest(t0_ms=t0_ms, window_end_ms=window_end_ms)
    for traj in trajectories:
        if not traj.trades and not traj.equity:
            man.excluded_no_data += 1
            continue
        # Inclusion: enough warm-up history BEFORE T0 (outcome-independent — measured at
        # T0 for everyone, blow-up or stable), so the detector has a real baseline.
        if not meets_baseline(traj, t_event_ms=t0_ms,
                              min_trades=min_trades, min_days=min_days):
            man.excluded_short_baseline += 1
            continue
        # Outcome from post-T0 data only; BUT drawdown measured against the GENUINE peak —
        # seed the running peak with the pre-T0 max so a fall from a pre-T0 high is not
        # hidden by slicing (this is the anti-hindsight fix; without it blow-ups undercount).
        pre_t0_peak = max((p.value for p in traj.equity if p.time < t0_ms),
                          default=float("-inf"))
        post_eq = [p for p in traj.equity if p.time >= t0_ms]
        post_tr = [t for t in traj.trades if t.time >= t0_ms]
        t_blow = forward_only_blowup_time(post_eq, post_tr, dd_pct, recovery_frac,
                                          recovery_horizon_ms, initial_peak=pre_t0_peak)
        if t_blow is not None and t_blow > window_end_ms:
            t_blow = None  # blow-up outside study window -> stable within window
        pre = [t for t in traj.trades if t.time < t0_ms]
        man.members.append(CohortMember(
            address=traj.address,
            label="blowup" if t_blow is not None else "stable",
            blowup_time=t_blow,
            event_cluster=_utc_day(t_blow) if t_blow is not None else None,
            baseline_trades=len(pre),
            baseline_days=(t0_ms - pre[0].time) / 86_400_000 if pre else 0.0))
    return man
```

- [ ] **Step 4: Run to verify pass** → 2 passed.

- [ ] **Step 5: Commit**

```bash
git add research/hyperliquid/universe.py research/hyperliquid/tests/test_universe.py
git commit -m "feat(hl): frozen-T0 cohort labeling (future-determined, event clusters, exclusions)"
```

---

## Task 8: CLI — enumerate universe → manifest + decision report

**Note on the universe snapshot (transparency, spec §6):** the official API exposes only the *current* leaderboard. To freeze at a past T₀ we assemble candidate addresses offline (current leaderboard + public liquidation trackers + large-trade feeds), then **include only addresses whose first fill ≤ T₀** (verifiable from their fills), and label outcomes from post-T₀ data. The CLI accepts that candidate list as a file; how the file was built is recorded in the report (no hidden enumeration).

**Files:**
- Create: `research/hyperliquid/__main__.py`
- Test: `research/hyperliquid/tests/test_cli.py` (smoke, uses FakeTransport + a 1-address list)

- [ ] **Step 1: Write a smoke test**

```python
# research/hyperliquid/tests/test_cli.py
import json
from research.hyperliquid.__main__ import run

def test_cli_emits_manifest(tmp_path, fake_transport_cls, raw_fills, raw_portfolio, raw_ledger, raw_orders):
    addrs = tmp_path / "addrs.txt"; addrs.write_text("0xabc\n")
    ft = fake_transport_cls([
        (lambda b: b["type"] == "userFillsByTime", raw_fills),
        (lambda b: b["type"] == "portfolio", raw_portfolio),
        (lambda b: b["type"] == "historicalOrders", raw_orders),
        (lambda b: b["type"] == "userNonFundingLedgerUpdates", raw_ledger),
    ])
    out = tmp_path / "cohort.json"
    man = run(addrs_path=str(addrs), t0_ms=1, window_end_ms=10**13,
              out_path=str(out), transport=ft, archive_dir=str(tmp_path/"arch"),
              dd_pct=0.5, recovery_frac=0.8, recovery_horizon_ms=86_400_000,
              min_trades=1, min_days=0.0)
    saved = json.loads(out.read_text())
    assert "base_rate" in saved and "effective_n_events" in saved
    assert saved["t0_ms"] == 1
```

- [ ] **Step 2: Run to verify fail** → FAIL.

- [ ] **Step 3: Implement `__main__.py`** (programmatic `run()` + argparse wrapper)

```python
# research/hyperliquid/__main__.py
from __future__ import annotations
import argparse, json
from dataclasses import asdict
from pathlib import Path
from research.hyperliquid.client import HyperliquidClient
from research.hyperliquid.trajectory import build_trajectory
from research.hyperliquid.universe import label_cohort

def run(addrs_path, t0_ms, window_end_ms, out_path, transport=None,
        archive_dir="research/hyperliquid/_archive", dd_pct=0.5, recovery_frac=0.8,
        recovery_horizon_ms=86_400_000, min_trades=30, min_days=7.0):
    c = HyperliquidClient(transport=transport, archive_dir=archive_dir)
    addrs = [a.strip() for a in Path(addrs_path).read_text().splitlines()
             if a.strip() and not a.strip().startswith("#")]
    trajs, n_truncated = [], 0
    for a in addrs:
        fills = c.fetch_user_fills_by_time(a, start_ms=0)
        if c.last_fetch_truncated:        # 10k-cap hit => truncated history (selection-bias line)
            n_truncated += 1
        trajs.append(build_trajectory(a, fills, c.fetch_portfolio(a),
                                      c.fetch_ledger(a, start_ms=0),
                                      c.fetch_historical_orders(a)))
    man = label_cohort(trajs, t0_ms, window_end_ms, dd_pct, recovery_frac,
                       recovery_horizon_ms, min_trades, min_days)
    payload = {"t0_ms": man.t0_ms, "window_end_ms": man.window_end_ms,
               "base_rate": man.base_rate, "effective_n_events": man.effective_n_events,
               "n_blowup": len(man.blowups), "n_stable": len(man.stable),
               "excluded_short_baseline": man.excluded_short_baseline,
               "excluded_no_data": man.excluded_no_data,
               "n_truncated_10k_cap": n_truncated,
               "members": [asdict(m) for m in man.members]}
    Path(out_path).write_text(json.dumps(payload, indent=2))
    return man

if __name__ == "__main__":   # pragma: no cover
    p = argparse.ArgumentParser()
    p.add_argument("--addrs", required=True); p.add_argument("--t0-ms", type=int, required=True)
    p.add_argument("--window-end-ms", type=int, required=True)
    p.add_argument("--out", default="research/hyperliquid/cohort.json")
    p.add_argument("--min-trades", type=int, default=30); p.add_argument("--min-days", type=float, default=7.0)
    a = p.parse_args()
    man = run(a.addrs, a.t0_ms, a.window_end_ms, a.out,
              min_trades=a.min_trades, min_days=a.min_days)
    print(f"members={len(man.members)} base_rate={man.base_rate:.3f} "
          f"effective_n_events={man.effective_n_events} "
          f"excluded_short={man.excluded_short_baseline}")
```

- [ ] **Step 4: Run to verify pass** → `python -m pytest research/hyperliquid/tests/test_cli.py -v` → passed. Then full module: `python -m pytest research/hyperliquid/tests/ -v` → all green.

- [ ] **Step 5: Commit**

```bash
git add research/hyperliquid/__main__.py research/hyperliquid/tests/test_cli.py
git commit -m "feat(hl): cohort-enumeration CLI (manifest + base rate + effective-N)"
```

---

## Task 9: Decision gate — real run + COHORT-REPORT.md (go/no-go for Plan 2/3)

This is the spec §14 phase-1 exit gate. Run the pipeline against a real frozen universe and write the report a human reads to decide whether the paper is viable.

**Files:**
- Create: `research/hyperliquid/candidates_t0.txt` (assembled address list; document sources at top as comments)
- Create: `research/hyperliquid/COHORT-REPORT.md`

- [ ] **Step 1 (MANUAL / offline — not a 2–5 min code step): Assemble the candidate address list**

Collect from: current Hyperliquid leaderboard, public liquidation trackers (CoinGlass/HyperTracker), and large-trade feeds. Save addresses (one per line) to `research/hyperliquid/candidates_t0.txt`, with header comments (`#`) naming each source + collection date. Pick T₀ to predate ≥ several distinct volatility regimes within the window the 10k-fill cap allows.
**Acceptance:** ≥ N candidate addresses (N fixed in the pre-registration commit), every source cited in the file header, and each address's first fill confirmed ≤ T₀ (genuinely in the universe at T₀, not added later). Indeterminate-length research task — the `#`-prefixed header lines are skipped by the CLI loader.

- [ ] **Step 2: Run the enumerator for real**

Run:
```bash
python -m research.hyperliquid --addrs research/hyperliquid/candidates_t0.txt \
  --t0-ms <T0> --window-end-ms <END> --min-trades 30 --min-days 7 \
  --out research/hyperliquid/cohort.json
```
Expected: prints `members / base_rate / effective_n_events / excluded_short`. Raw responses archived under `research/hyperliquid/_archive/`.

- [ ] **Step 3: Write `COHORT-REPORT.md`** with: T₀ + window; universe size + how it was enumerated (named sources); n_blowup / n_stable / base_rate; **effective_n_events (independent liquidation-days)**; exclusion counts (short-baseline, no-data) as named selection-bias lines; the 10k-fill-cap impact (how many candidates truncated). State the go/no-go: **GO if there are enough blow-ups AND enough independent crash events (effective N) to power event-clustered stats; otherwise widen window/universe or escalate.**

- [ ] **Step 4: Verify archive + report exist**

Run: `python -c "import os; print(len(os.listdir('research/hyperliquid/_archive')))"` and confirm `COHORT-REPORT.md` is written. (No unit test — this is a human decision artifact.)

- [ ] **Step 5: Commit**

```bash
git add research/hyperliquid/candidates_t0.txt research/hyperliquid/cohort.json research/hyperliquid/COHORT-REPORT.md
git commit -m "chore(hl): real frozen-universe cohort run + go/no-go decision report"
```

> ⚠️ Do NOT archive the raw `_archive/` JSON unless it is small; otherwise add `research/hyperliquid/_archive/` to `.gitignore` and keep only a manifest of what was captured.

---

## Done criteria (Plan 1)
- `python -m pytest research/hyperliquid/tests/ -v` all green; logic units (normalize, blowup, universe) covered including the no-look-ahead test.
- A real `cohort.json` + `COHORT-REPORT.md` exist with base rate and effective-N.
- Raw responses archived (or a capture manifest) for reproducibility.
- Main suite untouched: `python -m pytest tests/ -q` still 1374 passing.
- **Decision recorded:** GO → Plan 2 (detector); NO-GO → widen universe/window or escalate to Sean.
