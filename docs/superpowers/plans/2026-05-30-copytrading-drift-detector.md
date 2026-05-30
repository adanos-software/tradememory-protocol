# Copy-Trading Drift Detector (Plan 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 3-axis behavioral-drift detector in an isolated `research/hyperliquid/detector/` package, calibrate it on synthetic (HMM) data to pre-registered Type-I/power targets, and produce the frozen-hyperparameter artifact that lets pre-registration Part 2 lock — without touching the real locked test set.

**Architecture:** Per-fill behavioral state machines emit 9 primitives; at each time-bucket close they are z-scored against a James-Stein shrinkage null, composed into 3 per-axis observations (Exposure↑ / Discipline↓ / Tilt↑) with synthetic-tuned weights, sign-flipped, and fed to a reused `tradememory.ssrt.core.MixtureSPRT` per axis. A Holm-min-gate + sustained-M counter raises a composite alert, filtered by a 70%-equity / pre-first-liquidation guard band. A label-blind 2-state HMM generator produces synthetic masters for grid calibration and an ablation sanity check.

**Tech Stack:** Python 3.10+, stdlib + `math` only (zero heavy deps, matching Plan 1), pytest. Reuses Plan 1 `research/hyperliquid/{models,normalize,trajectory,blowup}.py` and `src/tradememory/ssrt/core.py`.

**Spec:** `docs/superpowers/specs/2026-05-30-copytrading-drift-detector-design.md`
**Pre-registration:** `research/hyperliquid/PRE-REGISTRATION-DRAFT.md` (Part 1 LOCKED `92e343c`; Part 2 locks at the end of this plan).

---

## Hard constraints (every task)

- Branch `copytrading-drift-demo`. UTC everywhere. Commit + push each task (hook auto-pushes). Update CLAUDE.md after each phase.
- Detector code + tests isolated under `research/hyperliquid/detector/` + `research/hyperliquid/tests/detector/`. Run: `python -m pytest research/hyperliquid/tests/ -q`.
- The ONLY `src/` change is the §10 legacy-CUSUM rename (Phase 7), which must keep `python -m pytest tests/ -q` at **1374 passing**.
- `detector/**` may import ONLY: stdlib + `math`; `research.hyperliquid.{models,normalize,trajectory,blowup}`; `tradememory.ssrt.core.MixtureSPRT`. NEVER `tradememory.owm.*` (enforced by a test).
- The real locked test set is NOT read anywhere in this plan. All anchoring/tuning is on synthetic or the tuning split only.
- Determinism: every random draw takes an explicit `seed` argument. No wall-clock, no `random` without a seeded `random.Random(seed)`.

## File structure (created by this plan)

```
research/hyperliquid/detector/
  __init__.py              # exports public surface
  config.py                # DetectorConfig, BaselineStats, PrimitiveStats dataclasses
  bucketing.py             # split a Trajectory into ordered time buckets
  primitives.py            # per-bucket 9 behavioral primitive values (3 per axis)
  shrinkage.py             # James-Stein blend of self vs universe (mu, sigma)
  axis.py                  # z-score + weighted compose + sign → 3 axis observations
  sprt_axis.py             # per-axis MixtureSPRT wrapper (reuses ssrt.core)
  composite.py             # Holm-min-gate + sustained-M counter
  guard_band.py            # is_early(equity, peak, first_liq) predicate
  detector.py             # orchestration: Trajectory → alert stream
  hmm_synth.py             # label-blind 2-state HMM synthetic master generator
  calibration.py           # grid search → frozen tuple + JSON artifact
  ablation.py              # discipline-only mode + synthetic sanity harness
research/hyperliquid/tests/detector/
  __init__.py
  helpers.py               # bucket/stream builders for tests
  test_no_owm_imports.py
  test_config.py  test_bucketing.py  test_primitives.py  test_shrinkage.py
  test_axis.py  test_sprt_axis.py  test_composite.py  test_guard_band.py
  test_detector.py  test_hmm_synth.py  test_calibration.py  test_ablation.py
```

Data flow: `Trajectory → bucketing → primitives → shrinkage(z) → axis(compose+sign) → sprt_axis(p) → composite(Holm+M) → guard_band → alert stream`. The SAME `detector.py` consumes synthetic streams (calibration/ablation) and real trajectories (Plan 3).

---

## Phase 0 — Scaffolding & isolation guard

### Task 0: Package skeleton + import-isolation test

**Files:**
- Create: `research/hyperliquid/detector/__init__.py` (empty for now)
- Create: `research/hyperliquid/tests/detector/__init__.py` (empty)
- Test: `research/hyperliquid/tests/detector/test_no_owm_imports.py`

- [ ] **Step 1: Write the failing test** — AST-scan every `detector/*.py` and assert none import `tradememory.owm`.

```python
import ast, pathlib

DET = pathlib.Path(__file__).resolve().parents[2] / "detector"

def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom):
            yield node.module or ""

def test_detector_never_imports_owm():
    offenders = []
    for py in DET.glob("*.py"):
        for mod in _imported_modules(py):
            if mod.startswith("tradememory.owm"):
                offenders.append((py.name, mod))
    assert offenders == [], f"detector must not import owm: {offenders}"

def test_detector_only_allows_whitelisted_tradememory():
    # the only tradememory import allowed is the ssrt engine
    bad = []
    for py in DET.glob("*.py"):
        for mod in _imported_modules(py):
            if mod.startswith("tradememory.") and not mod.startswith("tradememory.ssrt"):
                bad.append((py.name, mod))
    assert bad == [], f"only tradememory.ssrt allowed: {bad}"
```

- [ ] **Step 2: Run test to verify it fails** — Run: `python -m pytest research/hyperliquid/tests/detector/test_no_owm_imports.py -v`. Expected: FAIL (detector dir has no `.py` yet → `DET.glob` empty → actually passes vacuously). To make it a real RED, first create `detector/__init__.py` with a deliberate `# import tradememory.owm.changepoint` COMMENT only — skip; instead accept vacuous green here and rely on the guard catching real violations later. Mark this test as a standing guard, not a RED/GREEN pair.

- [ ] **Step 3: Create the package files** — `detector/__init__.py` and `tests/detector/__init__.py` empty.

- [ ] **Step 4: Run** — `python -m pytest research/hyperliquid/tests/detector/ -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add research/hyperliquid/detector/__init__.py research/hyperliquid/tests/detector/
git commit -m "feat(hl-detector): package skeleton + owm import-isolation guard"
```

---

### Task 1: Config dataclasses

**Files:**
- Create: `research/hyperliquid/detector/config.py`
- Test: `research/hyperliquid/tests/detector/test_config.py`

`PrimitiveStats` = one primitive's baseline (mean, std, n). `BaselineStats` = per-primitive self stats + per-primitive universe stats. `DetectorConfig` = frozen hyperparameters.

- [ ] **Step 1: Write the failing test**

```python
from research.hyperliquid.detector.config import (
    PrimitiveStats, BaselineStats, DetectorConfig, AXES, PRIMITIVES)

def test_axes_and_primitives_layout():
    assert AXES == ("exposure", "discipline", "tilt")
    # 3 primitives per axis, 9 total
    assert set(PRIMITIVES["exposure"]) == {"leverage", "notional_growth", "size_in_sigma"}
    assert set(PRIMITIVES["discipline"]) == {"stop_attach_rate", "reduce_only_rate", "mean_hold_hours"}
    assert set(PRIMITIVES["tilt"]) == {"topup_count", "loser_add_count", "fill_rate_spike"}

def test_config_defaults_match_prereg():
    cfg = DetectorConfig(bucket_ms=4*3600*1000, M=3,
                         tau={"exposure":0.3,"discipline":0.3,"tilt":0.3},
                         weights={a:{p:1/3 for p in PRIMITIVES[a]} for a in AXES},
                         kappa=14, burn_in=20)
    assert cfg.alpha == 0.01          # pre-reg #12
    assert cfg.guard_x == 0.70        # pre-reg #14
    assert cfg.holm_gate == cfg.alpha/3
```

- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3: Implement**

```python
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
```

- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hl-detector): config dataclasses (axes, primitives, DetectorConfig)`

---

## Phase 1 — Bucketing, shrinkage, primitives

### Task 2: Bucketing

**Files:**
- Create: `research/hyperliquid/detector/bucketing.py`
- Create: `research/hyperliquid/tests/detector/helpers.py`
- Test: `research/hyperliquid/tests/detector/test_bucketing.py`

A `Bucket` holds the fills, ledger events, and the bucket's `[start_ms, end_ms)`. `bucketize` walks a `Trajectory` from `origin_ms` in `bucket_ms` steps to `end_ms`, assigning each fill/ledger event to its bucket. Equity is sampled as "latest equity point at or before bucket end" (carry-forward).

- [ ] **Step 1: helpers.py** (test util, shared by later tasks)

```python
from research.hyperliquid.models import Trade, EquityPoint, LedgerEvent, Trajectory

def mk_trade(t_ms, coin="BTC", direction="Open Long", px=100.0, sz=1.0,
             closed_pnl=0.0, start_position=0.0, liq=False):
    return Trade(time=t_ms, coin=coin, direction=direction, px=px, sz=sz,
                 closed_pnl=closed_pnl, start_position=start_position, is_liquidation=liq)

def mk_eq(points):  # points: list[(t_ms, value)]
    return [EquityPoint(t, v) for t, v in points]

def mk_traj(trades=(), equity=(), ledger=(), stop_rate=0.0):
    trades = sorted(trades, key=lambda t: t.time)
    return Trajectory(address="0xtest", trades=list(trades), equity=list(equity),
                      ledger=list(ledger), stop_order_rate=stop_rate,
                      first_trade_ms=trades[0].time if trades else 0,
                      last_trade_ms=trades[-1].time if trades else 0)
```

- [ ] **Step 2: Write the failing test**

```python
from research.hyperliquid.detector.bucketing import bucketize
from research.hyperliquid.tests.detector.helpers import mk_trade, mk_eq, mk_traj

H = 3600*1000

def test_fills_land_in_correct_buckets():
    traj = mk_traj(trades=[mk_trade(0), mk_trade(H+5), mk_trade(2*H+5)],
                   equity=mk_eq([(0,100),(H,90),(2*H,80)]))
    buckets = bucketize(traj, origin_ms=0, end_ms=3*H, bucket_ms=H)
    assert len(buckets) == 3
    assert [len(b.fills) for b in buckets] == [1, 1, 1]
    assert buckets[0].start_ms == 0 and buckets[0].end_ms == H

def test_equity_is_carry_forward_at_bucket_end():
    traj = mk_traj(equity=mk_eq([(0,100),(H+10,50)]))
    buckets = bucketize(traj, origin_ms=0, end_ms=3*H, bucket_ms=H)
    # bucket 0 ends at H: latest point <= H is (0,100); bucket 1 ends 2H: (H+10,50)
    assert buckets[0].equity_end == 100
    assert buckets[1].equity_end == 50
    assert buckets[2].equity_end == 50   # carry-forward, no new point

def test_empty_when_origin_ge_end():
    assert bucketize(mk_traj(), origin_ms=10, end_ms=10, bucket_ms=H) == []
```

- [ ] **Step 3: Implement**

```python
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class Bucket:
    start_ms: int
    end_ms: int
    fills: list = field(default_factory=list)
    ledger: list = field(default_factory=list)
    equity_end: float | None = None

def bucketize(traj, origin_ms, end_ms, bucket_ms):
    if origin_ms >= end_ms:
        return []
    n = (end_ms - origin_ms + bucket_ms - 1) // bucket_ms
    buckets = [Bucket(origin_ms + i*bucket_ms, origin_ms + (i+1)*bucket_ms)
               for i in range(n)]
    def idx(t):
        return (t - origin_ms) // bucket_ms
    for tr in traj.trades:
        if origin_ms <= tr.time < end_ms:
            buckets[idx(tr.time)].fills.append(tr)
    for ev in traj.ledger:
        if origin_ms <= ev.time < end_ms:
            buckets[idx(ev.time)].ledger.append(ev)
    eq = sorted(traj.equity, key=lambda p: p.time)
    j, last = 0, None
    for b in buckets:
        while j < len(eq) and eq[j].time <= b.end_ms:
            last = eq[j].value
            j += 1
        b.equity_end = last
    return buckets
```

- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hl-detector): time-bucketize trajectory with carry-forward equity`

---

### Task 3: James-Stein shrinkage

**Files:**
- Create: `research/hyperliquid/detector/shrinkage.py`
- Test: `research/hyperliquid/tests/detector/test_shrinkage.py`

`blend(self_stats, universe_stats, kappa)` → blended `(mu, sigma)` where `w = n/(n+kappa)`, `mu = w*mu_self + (1-w)*mu_univ`, `sigma` via inverse-variance combine of the two scaled by the same weights, floored to avoid zero-division.

- [ ] **Step 1: Write the failing test**

```python
from research.hyperliquid.detector.config import PrimitiveStats
from research.hyperliquid.detector.shrinkage import blend

def test_no_self_history_is_all_universe():
    s = PrimitiveStats(mean=5.0, std=2.0, n=0)
    u = PrimitiveStats(mean=1.0, std=1.0, n=999)
    mu, sigma = blend(s, u, kappa=14)
    assert mu == 1.0 and sigma == 1.0

def test_large_self_history_approaches_self():
    s = PrimitiveStats(mean=5.0, std=2.0, n=10_000)
    u = PrimitiveStats(mean=1.0, std=1.0, n=999)
    mu, sigma = blend(s, u, kappa=14)
    assert abs(mu - 5.0) < 0.01

def test_sigma_floored_positive():
    s = PrimitiveStats(mean=0.0, std=0.0, n=5)
    u = PrimitiveStats(mean=0.0, std=0.0, n=5)
    _, sigma = blend(s, u, kappa=14)
    assert sigma > 0
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**

```python
from __future__ import annotations

SIGMA_FLOOR = 1e-9

def blend(self_stats, universe_stats, kappa):
    n = max(0, self_stats.n)
    w = n / (n + kappa) if (n + kappa) > 0 else 0.0
    mu = w * self_stats.mean + (1.0 - w) * universe_stats.mean
    # weighted variance combine (same shrinkage weight on the variance scale)
    var = w * (self_stats.std ** 2) + (1.0 - w) * (universe_stats.std ** 2)
    sigma = max(SIGMA_FLOOR, var ** 0.5)
    return mu, sigma
```

- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hl-detector): James-Stein self/universe baseline blend`

---

### Task 4: Primitives — Exposure axis

**Files:**
- Create: `research/hyperliquid/detector/primitives.py`
- Test: `research/hyperliquid/tests/detector/test_primitives.py`

`primitives.py` holds a `PrimitiveState` that walks fills chronologically (tracking signed position per coin) and, given a `Bucket`, returns the 9 primitive values. This task does the **Exposure** three: `leverage`, `notional_growth`, `size_in_sigma`. Subsequent tasks add Discipline & Tilt to the SAME function (extend, re-run all primitive tests).

Definitions (spec §4):
- `leverage` = `abs(notional_after_last_fill) / equity_end`; notional = `abs(signed_position) * last_px`. Carry-forward if bucket empty.
- `notional_growth` = `(abs(pos_end) - abs(pos_start)) * ref_px / equity_end` (per-bucket Δ; ref_px = last px in bucket or carried).
- `size_in_sigma` = `max(|sz| in bucket) / coin_return_std`, where `coin_return_std` is the rolling realized-return std passed in via a `coin_sigma` lookup (pre-computed; fall back to pooled when <14d — pooled value supplied by caller). 0 when no fill.

- [ ] **Step 1: Write the failing test**

```python
from research.hyperliquid.detector.primitives import PrimitiveState
from research.hyperliquid.detector.bucketing import bucketize
from research.hyperliquid.tests.detector.helpers import mk_trade, mk_eq, mk_traj

H = 3600*1000

def test_leverage_uses_notional_over_equity():
    # open 2 BTC @ 100 → notional 200; equity 100 → leverage 2.0
    traj = mk_traj(trades=[mk_trade(5, coin="BTC", direction="Open Long", px=100, sz=2,
                                    start_position=0)],
                   equity=mk_eq([(0,100),(H,100)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={"BTC": 1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["leverage"] == 2.0

def test_leverage_carry_forward_when_empty():
    traj = mk_traj(trades=[mk_trade(5, px=100, sz=2)],
                   equity=mk_eq([(0,100),(H,100),(2*H,100)]))
    buckets = bucketize(traj, 0, 2*H, H)
    st = PrimitiveState(coin_sigma={"BTC":1.0}, pooled_sigma=1.0)
    st.bucket_values(buckets[0])
    vals1 = st.bucket_values(buckets[1])   # no fills → carry prior position
    assert vals1["leverage"] == 2.0

def test_size_in_sigma_scales_by_coin_vol():
    traj = mk_traj(trades=[mk_trade(5, coin="ETH", px=10, sz=4)],
                   equity=mk_eq([(0,100),(H,100)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={"ETH": 2.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["size_in_sigma"] == 2.0   # |sz|=4 / sigma=2
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** (Exposure only; Discipline/Tilt keys return 0.0 placeholders so the dict shape is stable)

```python
from __future__ import annotations
from research.hyperliquid.detector.config import PRIMITIVES, AXES

def _signed(direction, sz):
    d = direction.lower()
    s = abs(sz)
    if "open long" in d or "buy" in d or ("long" in d and "close" not in d):
        return +s
    if "open short" in d or "sell" in d or ("short" in d and "close" not in d):
        return -s
    if "close long" in d:
        return -s
    if "close short" in d:
        return +s
    return 0.0

class PrimitiveState:
    """Walks fills in time order, tracking signed position per coin.
    bucket_values(bucket) returns the 9 primitive values at that bucket's close."""
    def __init__(self, coin_sigma, pooled_sigma):
        self.coin_sigma = coin_sigma
        self.pooled_sigma = max(1e-9, pooled_sigma)
        self.pos = {}            # coin -> signed position
        self.last_px = {}        # coin -> last fill px
        self._prev_abs_notional = 0.0

    def _abs_notional(self):
        return sum(abs(p) * self.last_px.get(c, 0.0) for c, p in self.pos.items())

    def bucket_values(self, bucket):
        abs_notional_start = self._abs_notional()
        for tr in bucket.fills:
            self.pos[tr.coin] = self.pos.get(tr.coin, 0.0) + _signed(tr.direction, tr.sz)
            self.last_px[tr.coin] = tr.px
        eq = bucket.equity_end or 1e-9
        abs_notional_end = self._abs_notional()
        leverage = abs_notional_end / eq
        notional_growth = (abs_notional_end - abs_notional_start) / eq
        max_sz = max((abs(tr.sz) for tr in bucket.fills), default=0.0)
        if bucket.fills:
            sig = self.coin_sigma.get(bucket.fills[-1].coin, self.pooled_sigma)
        else:
            sig = self.pooled_sigma
        size_in_sigma = max_sz / max(1e-9, sig)
        return {
            "leverage": leverage,
            "notional_growth": notional_growth,
            "size_in_sigma": size_in_sigma,
            # placeholders filled in Tasks 5-6
            "stop_attach_rate": 0.0, "reduce_only_rate": 0.0, "mean_hold_hours": 0.0,
            "topup_count": 0.0, "loser_add_count": 0.0, "fill_rate_spike": 0.0,
        }
```

- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hl-detector): exposure primitives (leverage, notional growth, size-in-sigma)`

---

### Task 5: Primitives — Discipline axis (order-level stop rate)

**Files:** Modify `research/hyperliquid/detector/primitives.py`; extend `test_primitives.py`.

Discipline (spec §4 + Data-source note): `stop_attach_rate` reads **order-level** data — fraction of opening fills in the bucket that have a live trigger/TP-SL order concurrently. `PrimitiveState` gains a `live_stop_window(t)` check fed by the bucket's orders. `reduce_only_rate` = fraction of fills that shrink `|position|`. `mean_hold_hours` = mean closed-position lifetime in the bucket (tracked via open timestamps). All carry-forward when no relevant fill.

> Bucketing must also carry orders. Extend `Bucket` with `orders: list` and `bucketize` to assign `raw_orders`-derived order events (need an order timestamp). Pass orders into `bucketize` as a normalized list `[{coin, ts, is_trigger}]` from a NEW helper `normalize.order_events(raw_orders)` (added in this task, in `research/hyperliquid/normalize.py` — allowed: it's a Plan-1 module, additive only, run main suite is NOT needed since research pkg is isolated, but run `python -m pytest research/hyperliquid/tests/ -q`).

- [ ] **Step 1: Write the failing test**

```python
def test_stop_attach_rate_counts_opening_fills_with_live_trigger():
    # opening fill at t=5 with a live trigger order in the same bucket → rate 1.0
    from research.hyperliquid.detector.primitives import PrimitiveState
    from research.hyperliquid.detector.bucketing import bucketize
    from research.hyperliquid.tests.detector.helpers import mk_trade, mk_eq, mk_traj
    H = 3600*1000
    traj = mk_traj(trades=[mk_trade(5, coin="BTC", direction="Open Long", px=100, sz=1)],
                   equity=mk_eq([(0,100),(H,100)]))
    buckets = bucketize(traj, 0, H, H, orders=[{"coin":"BTC","ts":4,"is_trigger":True}])
    st = PrimitiveState(coin_sigma={"BTC":1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["stop_attach_rate"] == 1.0

def test_reduce_only_rate_detects_position_shrink():
    from research.hyperliquid.detector.primitives import PrimitiveState
    from research.hyperliquid.detector.bucketing import bucketize
    from research.hyperliquid.tests.detector.helpers import mk_trade, mk_eq, mk_traj
    H = 3600*1000
    traj = mk_traj(trades=[mk_trade(2, direction="Open Long", px=100, sz=2),
                           mk_trade(6, direction="Close Long", px=100, sz=1)],
                   equity=mk_eq([(0,100),(H,100)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={"BTC":1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["reduce_only_rate"] == 0.5   # 1 of 2 fills shrank |pos|
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — add `normalize.order_events`; extend `bucketize(..., orders=None)` to attach `orders` per bucket by `ts`; in `bucket_values`, compute the three Discipline primitives. Track per-coin open time for hold duration; a fill that reduces `|pos|` increments reduce-only count and closes a hold (records elapsed hours). `stop_attach_rate` = opening fills with any bucket order where `is_trigger` for that coin / total opening fills (carry-forward last rate when no opening fill).
- [ ] **Step 4: Run** → PASS (and re-run all of `test_primitives.py`).
- [ ] **Step 5: Commit** `feat(hl-detector): discipline primitives (stop-attach, reduce-only, hold time)`

---

### Task 6: Primitives — Tilt axis

**Files:** Modify `primitives.py`; extend `test_primitives.py`.

Tilt (spec §4): `topup_count` = count of `deposit`-type ledger events in the bucket. `loser_add_count` = count of fills that increase `|position|` while the position carries unrealized loss vs running avg-entry. `fill_rate_spike` = `bucket_fill_count / trailing_24h_mean_fill_count` (trailing mean tracked across buckets; 0 when denom 0). All three are per-bucket aggregates (reset each bucket; `fill_rate_spike` uses a rolling 24h fill history).

- [ ] **Step 1: Write the failing test**

```python
def test_topup_count_from_deposit_ledger():
    from research.hyperliquid.models import LedgerEvent
    from research.hyperliquid.detector.primitives import PrimitiveState
    from research.hyperliquid.detector.bucketing import bucketize
    from research.hyperliquid.tests.detector.helpers import mk_eq, mk_traj
    H = 3600*1000
    traj = mk_traj(equity=mk_eq([(0,100),(H,100)]),
                   ledger=[LedgerEvent(5,"deposit",500.0), LedgerEvent(6,"withdraw",100.0)])
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["topup_count"] == 1   # deposits only

def test_loser_add_counts_adding_into_losing_position():
    from research.hyperliquid.detector.primitives import PrimitiveState
    from research.hyperliquid.detector.bucketing import bucketize
    from research.hyperliquid.tests.detector.helpers import mk_trade, mk_eq, mk_traj
    H = 3600*1000
    # open long @100, price drops to 90 (loss), then add @90 → loser_add
    traj = mk_traj(trades=[mk_trade(2, direction="Open Long", px=100, sz=1),
                           mk_trade(6, direction="Open Long", px=90, sz=1)],
                   equity=mk_eq([(0,100),(H,80)]))
    buckets = bucketize(traj, 0, H, H)
    st = PrimitiveState(coin_sigma={"BTC":1.0}, pooled_sigma=1.0)
    vals = st.bucket_values(buckets[0])
    assert vals["loser_add_count"] == 1
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — track running avg-entry price per coin; a fill that increases `|pos|` while `mark (= fill px) is worse than avg-entry for the position side` increments `loser_add_count`. `topup_count` from `bucket.ledger` deposits. `fill_rate_spike` from a deque of per-bucket fill counts over the trailing 24h window.
- [ ] **Step 4: Run** → PASS (re-run full `test_primitives.py`).
- [ ] **Step 5: Commit** `feat(hl-detector): tilt primitives (topup, loser-add, fill-rate spike)`

---

## Phase 2 — Axis observation & per-axis mSPRT

### Task 7: Axis compose (z-score, weighted sum, sign)

**Files:**
- Create: `research/hyperliquid/detector/axis.py`
- Test: `research/hyperliquid/tests/detector/test_axis.py`

`axis_observations(prim_values, baseline, cfg)` → `{axis: signed_obs}`. Per primitive: `z = (value - mu_blend)/sigma_blend` (blend via shrinkage.blend). Weighted sum per axis with `cfg.weights`. Then sign: multiply exposure & tilt by `-1` (so "bad = mean below 0" for all three; discipline already negative when bad).

- [ ] **Step 1: Write the failing test**

```python
from research.hyperliquid.detector.config import (
    PrimitiveStats, BaselineStats, DetectorConfig, PRIMITIVES, AXES)
from research.hyperliquid.detector.axis import axis_observations

def _flat_baseline(mean=0.0, std=1.0, n=10_000):
    self_stats = {a: {p: PrimitiveStats(mean,std,n) for p in PRIMITIVES[a]} for a in AXES}
    univ = {a: {p: PrimitiveStats(0.0,1.0,9999) for p in PRIMITIVES[a]} for a in AXES}
    return BaselineStats(self_stats, univ)

def _cfg():
    return DetectorConfig(bucket_ms=1, M=1,
        tau={a:0.3 for a in AXES},
        weights={a:{p:1/3 for p in PRIMITIVES[a]} for a in AXES}, kappa=0)

def test_exposure_up_yields_negative_signed_obs():
    base = _flat_baseline()
    vals = {p: 0.0 for a in AXES for p in PRIMITIVES[a]}
    for p in PRIMITIVES["exposure"]:
        vals[p] = 3.0   # +3 sigma exposure = BAD
    obs = axis_observations(vals, base, _cfg())
    assert obs["exposure"] < 0      # sign-flipped → drift below null

def test_discipline_down_yields_negative_signed_obs():
    base = _flat_baseline()
    vals = {p: 0.0 for a in AXES for p in PRIMITIVES[a]}
    for p in PRIMITIVES["discipline"]:
        vals[p] = -2.0  # discipline dropped = BAD
    obs = axis_observations(vals, base, _cfg())
    assert obs["discipline"] < 0
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**

```python
from __future__ import annotations
from research.hyperliquid.detector.config import PRIMITIVES, AXES, BAD_DIR
from research.hyperliquid.detector.shrinkage import blend

def axis_observations(prim_values, baseline, cfg):
    out = {}
    for axis in AXES:
        acc = 0.0
        for p in PRIMITIVES[axis]:
            mu, sigma = blend(baseline.self_stats[axis][p],
                              baseline.universe_stats[axis][p], cfg.kappa)
            z = (prim_values[p] - mu) / sigma
            acc += cfg.weights[axis][p] * z
        # sign so that BAD drift maps to mean < 0 for the one-sided mSPRT
        out[axis] = acc * (-1.0 if BAD_DIR[axis] > 0 else +1.0)
    return out
```

- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hl-detector): axis compose with shrinkage z-score + sign convention`

---

### Task 8: Per-axis mSPRT wrapper

**Files:**
- Create: `research/hyperliquid/detector/sprt_axis.py`
- Test: `research/hyperliquid/tests/detector/test_sprt_axis.py`

Thin wrapper: one `MixtureSPRT(alpha=cfg.alpha, tau=cfg.tau[axis], sigma=1, null_mean=0, burn_in=cfg.burn_in)` per axis. `update(axis, signed_obs)` → p-value. Reuses the MC-validated engine; NO reimplementation.

> **burn_in semantics (do not "fix"):** `MixtureSPRT.burn_in` gates only the engine's own `RETIRE` *decision*; `.p_value` is always-valid and real even during burn_in. `AxisSPRT` returns it unconditionally and `Composite` (Task 9) has no separate burn_in gate, so the composite may start counting fires before an axis clears burn_in. This is intentional — the synthetic Type-I suite measures the resulting false-alarm rate and the calibrated M absorbs it (spec R2). Adding burn_in masking would silently change calibration.

- [ ] **Step 1: Write the failing test**

```python
from research.hyperliquid.detector.config import DetectorConfig, AXES, PRIMITIVES
from research.hyperliquid.detector.sprt_axis import AxisSPRT

def _cfg(burn_in=5):
    return DetectorConfig(bucket_ms=1, M=1, tau={a:1.0 for a in AXES},
        weights={a:{p:1/3 for p in PRIMITIVES[a]} for a in AXES}, kappa=0, burn_in=burn_in)

def test_sustained_negative_drift_drives_pvalue_below_alpha():
    sprt = AxisSPRT(_cfg())
    p = 1.0
    for _ in range(60):
        p = sprt.update("exposure", -1.5)   # strong sustained bad drift
    assert p < 0.01

def test_flat_zero_keeps_pvalue_high():
    sprt = AxisSPRT(_cfg())
    p = 1.0
    for _ in range(60):
        p = sprt.update("discipline", 0.0)
    assert p > 0.01

def test_positive_obs_never_alerts_one_sided():
    sprt = AxisSPRT(_cfg())
    p = 1.0
    for _ in range(60):
        p = sprt.update("tilt", +2.0)   # "good" direction → one-sided no-alert
    assert p == 1.0
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**

```python
from __future__ import annotations
from tradememory.ssrt.core import MixtureSPRT
from research.hyperliquid.detector.config import AXES

class AxisSPRT:
    def __init__(self, cfg):
        self._sprt = {a: MixtureSPRT(alpha=cfg.alpha, tau=cfg.tau[a],
                                     sigma=1.0, null_mean=0.0, burn_in=cfg.burn_in)
                      for a in AXES}
    def update(self, axis, signed_obs):
        return self._sprt[axis].update(signed_obs).p_value
```

- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hl-detector): per-axis mSPRT wrapper reusing ssrt.core engine`

---

## Phase 3 — Composite, guard band, orchestration

### Task 9: Holm-min-gate + sustained-M composite

**Files:**
- Create: `research/hyperliquid/detector/composite.py`
- Test: `research/hyperliquid/tests/detector/test_composite.py`

`Composite(cfg)` tracks a sustained counter. `step(p_by_axis)` → `(fired, alert_raised, carrying_axis)`. Fires this bucket iff `min(p) <= cfg.holm_gate`. Counter increments on fire, resets on miss; `alert_raised` True at first bucket where counter reaches `cfg.M`. `carrying_axis` = argmin axis.

- [ ] **Step 1: Write the failing test**

```python
from research.hyperliquid.detector.config import DetectorConfig, AXES, PRIMITIVES
from research.hyperliquid.detector.composite import Composite

def _cfg(M):
    return DetectorConfig(bucket_ms=1, M=M, tau={a:1.0 for a in AXES},
        weights={a:{p:1/3 for p in PRIMITIVES[a]} for a in AXES}, kappa=0)

def test_alert_after_M_consecutive_fires():
    comp = Composite(_cfg(M=3))
    hot = {"exposure":0.001, "discipline":1.0, "tilt":1.0}   # min < 0.00333
    r1 = comp.step(hot); r2 = comp.step(hot); r3 = comp.step(hot)
    assert (r1.alert_raised, r2.alert_raised, r3.alert_raised) == (False, False, True)
    assert r3.carrying_axis == "exposure"

def test_miss_resets_counter():
    comp = Composite(_cfg(M=2))
    hot = {"exposure":0.001, "discipline":1.0, "tilt":1.0}
    cold = {"exposure":0.9, "discipline":0.9, "tilt":0.9}
    comp.step(hot); comp.step(cold)         # reset
    r = comp.step(hot)
    assert r.alert_raised is False          # only 1 consecutive after reset

def test_alert_latches_once():
    comp = Composite(_cfg(M=1))
    hot = {"exposure":0.001, "discipline":1.0, "tilt":1.0}
    assert comp.step(hot).alert_raised is True
    assert comp.step(hot).alert_raised is False   # already latched
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class CompositeStep:
    fired: bool
    alert_raised: bool
    carrying_axis: str | None

class Composite:
    def __init__(self, cfg):
        self.cfg = cfg
        self.counter = 0
        self.latched = False
    def step(self, p_by_axis):
        carrying = min(p_by_axis, key=p_by_axis.get)
        fired = p_by_axis[carrying] <= self.cfg.holm_gate
        self.counter = self.counter + 1 if fired else 0
        alert = False
        if not self.latched and fired and self.counter >= self.cfg.M:
            alert = True
            self.latched = True
        return CompositeStep(fired=fired, alert_raised=alert,
                             carrying_axis=carrying if fired else None)
```

- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hl-detector): Holm-min-gate + sustained-M composite alert`

---

### Task 10: Guard band

**Files:**
- Create: `research/hyperliquid/detector/guard_band.py`
- Test: `research/hyperliquid/tests/detector/test_guard_band.py`

`is_early(equity, running_peak, bucket_end_ms, first_liq_ms, guard_x)` → bool: `equity/peak >= guard_x AND (first_liq_ms is None or bucket_end_ms < first_liq_ms)`.

- [ ] **Step 1: Write the failing test**

```python
from research.hyperliquid.detector.guard_band import is_early

def test_healthy_and_preliq_is_early():
    assert is_early(equity=90, running_peak=100, bucket_end_ms=10,
                    first_liq_ms=100, guard_x=0.70) is True

def test_below_guard_x_is_late():
    assert is_early(equity=60, running_peak=100, bucket_end_ms=10,
                    first_liq_ms=None, guard_x=0.70) is False

def test_after_first_liquidation_is_late():
    assert is_early(equity=99, running_peak=100, bucket_end_ms=200,
                    first_liq_ms=100, guard_x=0.70) is False
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**

```python
from __future__ import annotations

def is_early(equity, running_peak, bucket_end_ms, first_liq_ms, guard_x):
    if running_peak <= 0:
        return False
    if equity / running_peak < guard_x:
        return False
    if first_liq_ms is not None and bucket_end_ms >= first_liq_ms:
        return False
    return True
```

- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hl-detector): guard band (70% peak + pre-first-liquidation)`

---

### Task 11: Detector orchestration

**Files:**
- Create: `research/hyperliquid/detector/detector.py`
- Test: `research/hyperliquid/tests/detector/test_detector.py`

`run_detector(traj, baseline, cfg, origin_ms, end_ms, coin_sigma, pooled_sigma, first_liq_ms=None, orders=None)` → list of `AlertRecord(bucket_end_ms, fired, alert_raised, is_early, carrying_axis)`. Wires bucketize → PrimitiveState → axis_observations → AxisSPRT → Composite → guard band, tracking running equity peak. Pure/deterministic.

- [ ] **Step 1: Write the failing test** — a hand-built drifting trajectory raises an EARLY composite alert before a constructed liquidation.

```python
from research.hyperliquid.detector.config import (
    PrimitiveStats, BaselineStats, DetectorConfig, PRIMITIVES, AXES)
from research.hyperliquid.detector.detector import run_detector
from research.hyperliquid.tests.detector.helpers import mk_trade, mk_eq, mk_traj

H = 3600*1000

def _baseline():
    s = {a:{p:PrimitiveStats(0.0,1.0,10_000) for p in PRIMITIVES[a]} for a in AXES}
    u = {a:{p:PrimitiveStats(0.0,1.0,9999) for p in PRIMITIVES[a]} for a in AXES}
    return BaselineStats(s,u)

def test_drifting_master_raises_early_alert():
    # leverage ramps each bucket while equity is still healthy → early exposure alert
    trades, eqpts = [], [(0, 100.0)]
    pos = 0.0
    for i in range(40):
        trades.append(mk_trade(i*H+5, coin="BTC", direction="Open Long", px=100, sz=2))
        eqpts.append(((i+1)*H, 100.0))   # equity flat & healthy
    traj = mk_traj(trades=trades, equity=mk_eq(eqpts))
    cfg = DetectorConfig(bucket_ms=H, M=3, tau={a:0.3 for a in AXES},
        weights={a:{p:(1.0 if p=="leverage" else 0.0) for p in PRIMITIVES[a]} for a in AXES},
        kappa=0, burn_in=5)
    recs = run_detector(traj, _baseline(), cfg, origin_ms=0, end_ms=40*H,
                        coin_sigma={"BTC":1.0}, pooled_sigma=1.0, first_liq_ms=None)
    early = [r for r in recs if r.alert_raised and r.is_early]
    assert early and early[0].carrying_axis == "exposure"
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — iterate buckets; maintain `running_peak = max(running_peak, equity_end)`; build `AlertRecord` per bucket; only the FIRST `alert_raised` latches (Composite handles it). Return the full record list.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hl-detector): end-to-end detector orchestration → alert stream`

---

## Phase 4 — Synthetic generator

### Task 12: HMM 2-state synthetic master generator

**Files:**
- Create: `research/hyperliquid/detector/hmm_synth.py`
- Test: `research/hyperliquid/tests/detector/test_hmm_synth.py`

`SynthSpec(anchors, cov, delta, theta_onset, theta_persist, length, seed)` and `generate_stream(spec)` → a sequence of per-bucket 9-primitive value dicts + the onset bucket index (None for pure-Normal). Anchors = per-primitive (median, mad). Emissions = multivariate Gaussian via Cholesky of the PSD-projected correlation scaled by MAD-derived sigma. Drifting state shifts each primitive's mean by `delta * sign(bad_dir)` in MAD units. Seeded `random.Random`.

> Gaussian sampling without numpy: implement a small `_mvn_sample(mean, chol, rng)` using Box-Muller for standard normals and `mean + chol @ z`. Provide a `_cholesky(matrix)` (pure-Python) and `_psd_project(corr)` (eigenvalue clip — use a tiny Jacobi eigen-solver, or for the 9×9 keep it simple: symmetrize + add `epsilon*I` until Cholesky succeeds, which is sufficient for PSD repair here).

- [ ] **Step 1: Write the failing test**

```python
from research.hyperliquid.detector.hmm_synth import SynthSpec, generate_stream
from research.hyperliquid.detector.config import PRIMITIVES, AXES

def _anchors(mad=1.0):
    return {a:{p:{"median":0.0,"mad":mad} for p in PRIMITIVES[a]} for a in AXES}

def _identity_cov():
    keys = [p for a in AXES for p in PRIMITIVES[a]]
    return {k:{j:(1.0 if k==j else 0.0) for j in keys} for k in keys}

def test_pure_normal_stream_has_no_onset_and_is_centered():
    spec = SynthSpec(anchors=_anchors(), cov=_identity_cov(), delta=1.0,
                     theta_onset=0.0, theta_persist=0.99, length=2000, seed=1)
    stream, onset = generate_stream(spec)
    assert onset is None
    import statistics
    lev = [b["leverage"] for b in stream]
    assert abs(statistics.fmean(lev)) < 0.15   # centered near anchor median

def test_drifting_stream_shifts_axis_means_after_onset():
    spec = SynthSpec(anchors=_anchors(), cov=_identity_cov(), delta=1.0,
                     theta_onset=1.0, theta_persist=1.0, length=400, seed=2)  # onset at bucket 0
    stream, onset = generate_stream(spec)
    assert onset == 0
    import statistics
    # exposure bad_dir=+1 → leverage mean shifts UP by ~delta MAD
    assert statistics.fmean([b["leverage"] for b in stream]) > 0.5

def test_seed_determinism():
    spec = SynthSpec(anchors=_anchors(), cov=_identity_cov(), delta=1.0,
                     theta_onset=0.5, theta_persist=0.9, length=100, seed=7)
    a,_ = generate_stream(spec); b,_ = generate_stream(spec)
    assert a == b
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the HMM (single random onset for the power suite when `0 < theta_onset`; for `theta_onset==1.0` onset at bucket 0; `theta_onset==0.0` never drifts). Emit standard-normal vector, transform by Cholesky, add per-state mean (`median + delta*MAD*sign` in Drifting). Return `(stream, onset_idx)`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hl-detector): label-blind 2-state HMM synthetic master generator`

---

### Task 13: Synthetic stream → detector adapter

**Files:** Modify `detector.py` (add `run_detector_on_stream`); extend `test_detector.py`.

The calibration/ablation harnesses feed primitive-value streams directly (not Trajectories). Add `run_detector_on_stream(stream, baseline, cfg, first_liq_idx=None)` that skips bucketing/primitives and runs axis → sprt → composite → guard on a precomputed `stream` of 9-primitive dicts, treating bucket index as time. Guard band uses a synthetic equity proxy: streams carry no equity, so for synthetic, `is_early` is True until `first_liq_idx` (pure-Normal: always early; Drifting: early through the whole stream since we measure lead-time to onset, no liquidation modeled). Document this explicitly.

- [ ] **Step 1: Write the failing test**

```python
def test_run_on_stream_alerts_on_drift_after_onset():
    from research.hyperliquid.detector.hmm_synth import SynthSpec, generate_stream
    from research.hyperliquid.detector.detector import run_detector_on_stream
    from research.hyperliquid.detector.config import (
        PrimitiveStats, BaselineStats, DetectorConfig, PRIMITIVES, AXES)
    s={a:{p:PrimitiveStats(0.0,1.0,10_000) for p in PRIMITIVES[a]} for a in AXES}
    u={a:{p:PrimitiveStats(0.0,1.0,9999) for p in PRIMITIVES[a]} for a in AXES}
    base=BaselineStats(s,u)
    keys=[p for a in AXES for p in PRIMITIVES[a]]
    ident={k:{j:(1.0 if k==j else 0.0) for j in keys} for k in keys}
    spec=SynthSpec(anchors={a:{p:{"median":0.0,"mad":1.0} for p in PRIMITIVES[a]} for a in AXES},
                   cov=ident,
                   delta=2.0, theta_onset=1.0, theta_persist=1.0, length=200, seed=3)
    stream,onset=generate_stream(spec)
    cfg=DetectorConfig(bucket_ms=1, M=3, tau={a:0.3 for a in AXES},
        weights={a:{p:1/3 for p in PRIMITIVES[a]} for a in AXES}, kappa=0, burn_in=10)
    recs=run_detector_on_stream(stream, base, cfg)
    assert any(r.alert_raised for r in recs)
```

> In Step 3, refactor the shared `_anchors`/`_identity_cov` test builders into `helpers.py` as `anchors_flat()`/`identity_cov()` so Tasks 14 and 16 can import them (Task 14 uses exactly those names). The inline `ident` above is correct — it just becomes the shared helper.

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `run_detector_on_stream`; refactor `_anchors`/`_identity_cov` into `helpers.py`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hl-detector): synthetic-stream detector adapter + shared test helpers`

---

## Phase 5 — Calibration

### Task 14: Type-I & power measurement on synthetic suites

**Files:**
- Create: `research/hyperliquid/detector/calibration.py`
- Test: `research/hyperliquid/tests/detector/test_calibration.py`

`measure(cfg, anchors, cov, delta, n_streams, length, seed)` → `{type_i, power, median_lead_buckets}`. Type-I: `n_streams` pure-Normal streams (`theta_onset=0`), Type-I = fraction with any `alert_raised`. Power: `n_streams` single-onset Drifting streams, power = fraction alerted after onset; lead = `onset_idx... ` wait — lead-time for EARLY warning is measured as buckets the alert PRECEDES a (synthetic) blow-up; in the synthetic power suite we measure **detection latency** `alert_idx - onset_idx` and report power + latency (the real lead-time vs baselines is Plan 3). Keep `median_detection_latency_buckets`.

- [ ] **Step 1: Write the failing test** (small n, loose bounds — just exercises the machinery)

```python
from research.hyperliquid.detector.calibration import measure
from research.hyperliquid.detector.config import DetectorConfig, PRIMITIVES, AXES
from research.hyperliquid.tests.detector.helpers import anchors_flat, identity_cov

def _cfg(M=3):
    return DetectorConfig(bucket_ms=1, M=M, tau={a:0.3 for a in AXES},
        weights={a:{p:1/3 for p in PRIMITIVES[a]} for a in AXES}, kappa=0, burn_in=10)

def test_measure_reports_typei_and_power():
    res = measure(_cfg(), anchors_flat(), identity_cov(), delta=2.0,
                  n_streams=40, length=300, seed=11)
    assert 0.0 <= res["type_i"] <= 1.0
    assert 0.0 <= res["power"] <= 1.0
    # strong delta + small M → power should clearly exceed type-I
    assert res["power"] > res["type_i"]
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `measure` (loops `generate_stream` + `run_detector_on_stream`, aggregates). Add `anchors_flat`/`identity_cov` to `helpers.py`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hl-detector): synthetic Type-I/power/latency measurement`

---

### Task 15: Grid search + pickup rule + artifact

**Files:** Modify `calibration.py` (add `grid_search`, `pick_winner`, `run_calibration`); extend `test_calibration.py`.

`grid_search` enumerates `bucket ∈ {1h,4h,24h}` × `M ∈ {2,3,4,6,9,12}` (constrained `6h ≤ M·bucket ≤ 7d`) × `tau ∈ {0.3,1.0}` × `weights ∈ {equal, lda}` × `kappa ∈ {7,14,30}`, calling `measure` for each. `pick_winner` applies: keep tuples with `power≥0.70 ∧ type_i≤0.02` (relax to `≤0.05`, set `typeI_target_relaxed=True`); rank by (power desc, `M·bucket_hours` asc, dof asc). `run_calibration` writes `calibration_result.json` with full grid, winner, realized metrics, `power_by_delta` (δ∈{0.5,1.0,1.5}), and `typeI_target_relaxed`.

> The LDA weight option fits Fisher-LDA within each axis on a small synthetic Normal-vs-Drifting sample (ridge-regularized scatter; fall back to equal weights if conditioning fails). Implement `lda_weights(axis, anchors, cov, delta, seed)`; test its fallback path.

- [ ] **Step 1: Write the failing test**

```python
def test_pick_winner_prefers_power_then_short_floor():
    from research.hyperliquid.detector.calibration import pick_winner
    rows = [
        {"bucket_ms":4*3600*1000,"M":6,"power":0.80,"type_i":0.01,"dof":5,
         "tau":0.3,"weights":"equal","kappa":14},
        {"bucket_ms":1*3600*1000,"M":3,"power":0.80,"type_i":0.01,"dof":5,
         "tau":0.3,"weights":"equal","kappa":14},
    ]
    w, relaxed = pick_winner(rows)
    assert relaxed is False
    assert w["bucket_ms"] == 1*3600*1000   # same power → shorter M*bucket floor wins

def test_pick_winner_relaxes_typei_when_none_pass_strict():
    from research.hyperliquid.detector.calibration import pick_winner
    rows = [{"bucket_ms":3600*1000,"M":3,"power":0.75,"type_i":0.04,"dof":5,
             "tau":0.3,"weights":"equal","kappa":14}]
    w, relaxed = pick_winner(rows)
    assert relaxed is True and w is not None
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `grid_search`/`pick_winner`/`lda_weights`/`run_calibration`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hl-detector): calibration grid search + pickup rule + JSON artifact`

---

## Phase 6 — Ablation

### Task 16: Discipline-only mode + synthetic sanity

**Files:**
- Create: `research/hyperliquid/detector/ablation.py`
- Test: `research/hyperliquid/tests/detector/test_ablation.py`

`discipline_only_cfg(cfg)` returns a cfg whose exposure & tilt axes are masked. Masking is implemented in the detector path by forcing those axes' p-value to 1.0 — add a `mask_axes` set to `DetectorConfig` (default empty) and honor it in `AxisSPRT`/`Composite`. `ablation_sanity(anchors, cov, cfg, seed)` runs the 3 scenarios (A discipline-only drift, B full, C exposure+tilt) and returns, for Scenario A, `discipline_only_latency / full_latency` plus an event-clustered CI (bootstrap over synthetic onset clusters) that should exclude 0 — proving the harness can measure the ≥50% bar.

- [ ] **Step 1: Write the failing test**

```python
def test_mask_forces_axis_pvalue_high():
    from research.hyperliquid.detector.config import DetectorConfig, AXES, PRIMITIVES
    from research.hyperliquid.detector.sprt_axis import AxisSPRT
    cfg = DetectorConfig(bucket_ms=1, M=1, tau={a:1.0 for a in AXES},
        weights={a:{p:1/3 for p in PRIMITIVES[a]} for a in AXES}, kappa=0,
        burn_in=1, mask_axes=frozenset({"exposure","tilt"}))
    sprt = AxisSPRT(cfg)
    for _ in range(30):
        p_exp = sprt.update("exposure", -3.0)   # would normally alert
    assert p_exp == 1.0                          # masked → never contributes

def test_scenario_A_discipline_only_recovers_measurable_lead():
    from research.hyperliquid.detector.ablation import ablation_sanity
    from research.hyperliquid.tests.detector.helpers import anchors_flat, identity_cov
    from research.hyperliquid.detector.config import DetectorConfig, AXES, PRIMITIVES
    cfg = DetectorConfig(bucket_ms=1, M=3, tau={a:0.3 for a in AXES},
        weights={a:{p:1/3 for p in PRIMITIVES[a]} for a in AXES}, kappa=0, burn_in=10)
    res = ablation_sanity(anchors_flat(), identity_cov(), cfg, seed=5,
                          n_streams=60, length=300)
    assert res["scenario_A"]["ci_low"] > 0      # CI excludes 0 → bar is measurable
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — add `mask_axes: frozenset = frozenset()` to `DetectorConfig`; honor it (masked axis → p=1.0) in `AxisSPRT.update`; `ablation.py` with `discipline_only_cfg`, the 3-scenario runner, and a seeded cluster-bootstrap CI.
- [ ] **Step 4: Run** → PASS. Re-run full detector suite: `python -m pytest research/hyperliquid/tests/ -q`.
- [ ] **Step 5: Commit** `feat(hl-detector): discipline-only ablation + synthetic sanity (50% bar measurable)`

---

## Phase 7 — Legacy CUSUM rename (only src/ change)

### Task 17: Rename owm binary-CUSUM remnants (grep-first, alias, dual-read)

**Files:**
- Modify: `src/tradememory/owm/changepoint.py`
- Run: full main suite.

- [ ] **Step 1: Grep consumers** — Run: `git grep -n "cusum_alert\|cusum_value\|_cusum_" -- src tests`. Record every hit. Confirm (spec §10 + reviewer): no public REST/MCP surface exposes these (server.py / mcp_server.py have zero refs). If any NEW public consumer appears, STOP and surface to human.

> **Scope:** rename targets live in `src/tradememory/owm/changepoint.py` ONLY (the `_cusum_*` attributes + `ChangePointResult.cusum_alert`/`cusum_value`). The grep ALSO hits `src/tradememory/owm/drift.py` (a local `cusum_values` list variable + a docstring) — that is a DIFFERENT legacy DD-CUSUM construct; do NOT touch it.

- [ ] **Step 2: Run baseline** — `python -m pytest tests/ -q`. Expected: **1374 passed** (record the exact number/skips before touching anything).

- [ ] **Step 3: Rename internals + dual-read state + docstrings** — `_cusum_s→_legacy_cusum_s` etc.; keep public `ChangePointResult.cusum_alert`/`cusum_value` field NAMES; `from_state` reads both new and old JSON keys; update module + class docstrings to the spec §10 wording ("Legacy binary-CUSUM … NOT part of the copy-trading drift paper detector").

- [ ] **Step 4: Run** — `python -m pytest tests/ -q`. Expected: SAME count, **1374 passed**. If anything fails, fix the rename (do NOT change test expectations).

- [ ] **Step 5: Commit** `refactor(owm): mark legacy binary-CUSUM as pre-pivot, isolate from paper detector`

---

## Phase 8 — Run calibration & lock pre-registration Part 2

### Task 18: Execute calibration, freeze winner, lock pre-reg Part 2

**Files:**
- Create: `research/hyperliquid/detector/calibration_result.json` (artifact)
- Modify: `research/hyperliquid/PRE-REGISTRATION-DRAFT.md` (fill Part 2 values from the artifact)
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the calibration** — invoke `run_calibration` (a small `python -m research.hyperliquid.detector.calibration` entry or a one-off script under `scripts/research/`) with the pre-registered N (≥10,000 synthetic/cell for the final; a smaller smoke first). Anchors/cov come from the **tuning split** marginals — until Plan 3 enumerates the real tuning split, use the spec-sanctioned placeholder anchors flagged clearly as provisional, OR defer the FINAL numeric lock to the start of Plan 3 when the tuning split exists. **Decision point — STOP and ask Sean before proceeding past this step:** lock Part 2 on synthetic-only anchors now, vs. lock at Plan 3 start once tuning-split marginals are computed. (Recommended: compute tuning-split marginals first — they are outcome-blind and don't touch the locked test — then lock. Add a tiny Plan-3 pre-task for it.)

- [ ] **Step 2: Inspect the artifact** — confirm `power≥0.70`, `type_i≤0.05`, record `typeI_target_relaxed`, the winning `(bucket,M,tau,weights,kappa)`, and the `power_by_delta` curve.

- [ ] **Step 3: Fill pre-reg Part 2** — write the frozen values into `PRE-REGISTRATION-DRAFT.md` Part 2 table (#11–#15) + add the §13 lock list values from spec; mark Part 2 LOCKED with the date.

- [ ] **Step 4: Update CLAUDE.md** — Recent Changes + Current Status: detector built (N tests green), calibration winner, Part 2 locked, next = Plan 3.

- [ ] **Step 5: Commit (the timestamped pre-registration Part 2 record)**

```bash
git add research/hyperliquid/detector/calibration_result.json \
        research/hyperliquid/PRE-REGISTRATION-DRAFT.md CLAUDE.md
git commit -m "docs(hl): LOCK pre-registration Part 2 (detector hyperparameters) — synthetic-calibrated"
```

> This commit's hash is the Part-2 pre-registration record the paper cites. The real locked test is read ONLY after it exists (Plan 3).

---

## Definition of done

- `python -m pytest research/hyperliquid/tests/ -q` green (all detector + Plan-1 tests).
- `python -m pytest tests/ -q` still **1374 passed** after the §10 rename.
- `detector/` imports no `tradememory.owm.*` (guard test green).
- `calibration_result.json` exists with a winner meeting `power≥0.70 ∧ type_i≤0.05` and the relaxation flag recorded.
- Pre-registration Part 2 locked in a timestamped commit (or the Step-1 decision-point deferral explicitly approved by Sean).
- CLAUDE.md updated; every task committed + pushed on `copytrading-drift-demo`.

## Notes for the executor

- Reuse, don't reinvent: the mSPRT math lives in `tradememory.ssrt.core.MixtureSPRT` — wrap it, never copy it.
- Keep synthetic and real code paths identical through `axis → sprt → composite → guard` (Task 13 adapter only swaps the front end). Divergence here invalidates the calibration.
- No numpy/scipy — pure Python + `math` (matches Plan 1). The 9×9 Gaussian needs a tiny hand-rolled Cholesky; keep PSD repair simple (`+εI` until Cholesky succeeds).
- Every randomness path takes an explicit seed. Document the seed in the artifact.
- If the §10 grep finds a public consumer, STOP — that's the one place this plan can break production.
```

