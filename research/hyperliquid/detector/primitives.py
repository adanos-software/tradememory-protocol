"""Per-bucket behavioral primitive calculations.

PrimitiveState walks fills chronologically, tracking signed position per coin,
and returns all 9 primitive values at each bucket's close.

Axes:
  exposure   — leverage, notional_growth, size_in_sigma
  discipline — stop_attach_rate, reduce_only_rate, mean_hold_hours
  tilt       — topup_count, loser_add_count, fill_rate_spike
"""
from __future__ import annotations

from collections import deque


# ---------------------------------------------------------------------------
# Direction helper
# ---------------------------------------------------------------------------

def _signed(direction: str, sz: float) -> float:
    """Return signed size for a fill: positive = long-side, negative = short-side."""
    d = direction.lower()
    s = abs(sz)
    if "open long" in d or ("buy" in d and "close" not in d) or \
            ("long" in d and "open" in d):
        return +s
    if "open short" in d or ("sell" in d and "close" not in d) or \
            ("short" in d and "open" in d):
        return -s
    if "close long" in d:
        return -s
    if "close short" in d:
        return +s
    # generic buy/sell without open/close context
    if "buy" in d:
        return +s
    if "sell" in d:
        return -s
    return 0.0


# ---------------------------------------------------------------------------
# PrimitiveState
# ---------------------------------------------------------------------------

class PrimitiveState:
    """Stateful walker: call bucket_values(bucket) in chronological bucket order.

    Parameters
    ----------
    coin_sigma : dict[str, float]
        Per-coin daily-return std used for size_in_sigma normalisation.
    pooled_sigma : float
        Fallback std when a coin is not in coin_sigma.
    """

    def __init__(self, coin_sigma: dict, pooled_sigma: float) -> None:
        self.coin_sigma = coin_sigma
        self.pooled_sigma = max(1e-9, pooled_sigma)

        # --- Exposure state ---
        self._pos: dict[str, float] = {}       # signed position per coin
        self._last_px: dict[str, float] = {}   # last seen price per coin

        # --- Discipline state ---
        self._open_time: dict[str, float] = {}  # coin -> ms when pos first opened from flat
        self._prev_stop_attach_rate: float = 0.0
        self._prev_reduce_only_rate: float = 0.0
        self._prev_mean_hold_hours: float = 0.0

        # --- Tilt state ---
        # Rolling 24h fill-count window: deque of (bucket_end_ms, fill_count)
        self._fill_history: deque = deque()     # (bucket_end_ms, fill_count)
        self._prev_fill_rate_spike: float = 0.0

        # avg-entry tracking for loser_add
        self._avg_entry: dict[str, float] = {}  # coin -> weighted avg entry px

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _abs_notional(self) -> float:
        return sum(abs(p) * self._last_px.get(c, 0.0) for c, p in self._pos.items())

    def _is_opening(self, coin: str, delta: float) -> bool:
        """True if applying delta increases |position|."""
        pos_before = self._pos.get(coin, 0.0)
        pos_after = pos_before + delta
        return abs(pos_after) > abs(pos_before)

    def _is_closing_or_reducing(self, coin: str, delta: float) -> bool:
        """True if applying delta decreases |position|."""
        pos_before = self._pos.get(coin, 0.0)
        pos_after = pos_before + delta
        return abs(pos_after) < abs(pos_before)

    def _update_position(self, coin: str, delta: float, px: float) -> None:
        """Apply a fill delta to the position tracker and update avg-entry."""
        pos_before = self._pos.get(coin, 0.0)
        pos_after = pos_before + delta
        self._pos[coin] = pos_after
        self._last_px[coin] = px

        if abs(pos_after) > abs(pos_before):
            # Opening / adding — update avg-entry
            prev_avg = self._avg_entry.get(coin, px)
            prev_abs = abs(pos_before)
            add_abs = abs(delta)
            total_abs = prev_abs + add_abs
            self._avg_entry[coin] = (prev_avg * prev_abs + px * add_abs) / total_abs
        elif abs(pos_after) < 1e-12:
            # Fully closed — clear avg-entry and open-time
            self._avg_entry.pop(coin, None)
            self._open_time.pop(coin, None)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def bucket_values(self, bucket) -> dict[str, float]:
        """Compute all 9 primitives for *bucket* and advance state.

        Must be called in chronological bucket order.
        """
        H24_MS = 24 * 3600 * 1000

        # ----------------------------------------------------------------
        # Exposure — pre-fill snapshot for notional_growth
        # ----------------------------------------------------------------
        abs_notional_start = self._abs_notional()
        eq = bucket.equity_end if bucket.equity_end is not None else 1e-9
        eq = max(eq, 1e-9)

        # ----------------------------------------------------------------
        # Discipline trackers
        # ----------------------------------------------------------------
        opening_fills = 0
        opening_with_stop = 0
        reduce_fills = 0
        total_fills = len(bucket.fills)
        closed_lifetimes: list[float] = []

        # ----------------------------------------------------------------
        # Tilt trackers
        # ----------------------------------------------------------------
        loser_add_count = 0

        # ----------------------------------------------------------------
        # Build a set of coins that have a same-bucket trigger order
        # ----------------------------------------------------------------
        orders_list = getattr(bucket, "orders", []) or []
        trigger_coins: set[str] = {
            o["coin"] for o in orders_list if o.get("is_trigger")
        }

        # ----------------------------------------------------------------
        # Walk fills
        # ----------------------------------------------------------------
        max_sz = 0.0
        max_sz_coin = None

        for tr in bucket.fills:
            delta = _signed(tr.direction, tr.sz)
            coin = tr.coin

            # size_in_sigma must normalise the largest fill by ITS OWN coin's sigma,
            # not the last fill's coin (matters in multi-coin buckets).
            if abs(tr.sz) > max_sz:
                max_sz = abs(tr.sz)
                max_sz_coin = coin

            # Discipline: open-time tracking (before position update)
            pos_before = self._pos.get(coin, 0.0)
            if abs(pos_before) < 1e-12 and self._is_opening(coin, delta):
                # Opening from flat: record entry time
                self._open_time[coin] = tr.time

            # Tilt: loser-add check (before position update)
            if self._is_opening(coin, delta) and abs(pos_before) > 1e-12:
                avg = self._avg_entry.get(coin, tr.px)
                side = pos_before  # positive = long, negative = short
                is_loser = (side > 0 and tr.px < avg) or (side < 0 and tr.px > avg)
                if is_loser:
                    loser_add_count += 1

            # Discipline: close tracking (before position update, to record open_time)
            if self._is_closing_or_reducing(coin, delta):
                reduce_fills += 1
                ot = self._open_time.get(coin)
                if ot is not None:
                    pos_after = pos_before + delta
                    if abs(pos_after) < 1e-12:
                        # Full close
                        closed_lifetimes.append((tr.time - ot) / (3600 * 1000))
                        # open_time cleared inside _update_position

            # Discipline: opening-fill stop-attach
            if self._is_opening(coin, delta):
                opening_fills += 1
                if coin in trigger_coins:
                    opening_with_stop += 1

            # Apply position update
            self._update_position(coin, delta, tr.px)

        # ----------------------------------------------------------------
        # Exposure primitives
        # ----------------------------------------------------------------
        abs_notional_end = self._abs_notional()
        leverage = abs_notional_end / eq
        notional_growth = (abs_notional_end - abs_notional_start) / eq

        if bucket.fills:
            sig = self.coin_sigma.get(max_sz_coin, self.pooled_sigma)
        else:
            sig = self.pooled_sigma
        size_in_sigma = max_sz / max(1e-9, sig)

        # ----------------------------------------------------------------
        # Discipline primitives
        # ----------------------------------------------------------------
        if opening_fills > 0:
            stop_attach_rate = opening_with_stop / opening_fills
            self._prev_stop_attach_rate = stop_attach_rate
        else:
            stop_attach_rate = self._prev_stop_attach_rate

        if total_fills > 0:
            reduce_only_rate = reduce_fills / total_fills
            self._prev_reduce_only_rate = reduce_only_rate
        else:
            reduce_only_rate = self._prev_reduce_only_rate

        if closed_lifetimes:
            mean_hold_hours = sum(closed_lifetimes) / len(closed_lifetimes)
            self._prev_mean_hold_hours = mean_hold_hours
        else:
            mean_hold_hours = self._prev_mean_hold_hours

        # ----------------------------------------------------------------
        # Tilt primitives
        # ----------------------------------------------------------------
        topup_count = sum(
            1 for ev in bucket.ledger if ev.type == "deposit"
        )

        # fill_rate_spike: trim stale entries from rolling window
        cutoff_ms = bucket.end_ms - H24_MS
        while self._fill_history and self._fill_history[0][0] <= cutoff_ms:
            self._fill_history.popleft()

        # Compute trailing-24h mean BEFORE appending this bucket
        if self._fill_history:
            trailing_mean = sum(c for _, c in self._fill_history) / len(self._fill_history)
            fill_rate_spike = total_fills / max(1e-9, trailing_mean)
            self._prev_fill_rate_spike = fill_rate_spike
        else:
            fill_rate_spike = 0.0

        # Append current bucket
        self._fill_history.append((bucket.end_ms, total_fills))

        return {
            # Exposure
            "leverage": leverage,
            "notional_growth": notional_growth,
            "size_in_sigma": size_in_sigma,
            # Discipline
            "stop_attach_rate": stop_attach_rate,
            "reduce_only_rate": reduce_only_rate,
            "mean_hold_hours": mean_hold_hours,
            # Tilt
            "topup_count": float(topup_count),
            "loser_add_count": float(loser_add_count),
            "fill_rate_spike": fill_rate_spike,
        }
