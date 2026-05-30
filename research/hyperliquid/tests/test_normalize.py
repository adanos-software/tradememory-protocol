from research.hyperliquid.normalize import (
    normalize_fills, equity_curve, drawdown_series, ledger_events, stop_order_rate)


def test_normalize_marks_liquidation(raw_fills):
    trades = normalize_fills(raw_fills)
    assert len(trades) == 2
    assert trades[0].is_liquidation is False
    assert trades[1].is_liquidation is True
    assert trades[0].closed_pnl == -690.81


def test_equity_curve_parses_and_sorts(raw_portfolio):
    eq = equity_curve(raw_portfolio, period="perpAllTime")
    assert [p.value for p in eq] == [1000000.0, 1895650.0, 500000.0, 0.0]
    assert eq == sorted(eq, key=lambda p: p.time)


def test_drawdown_from_running_peak(raw_portfolio):
    eq = equity_curve(raw_portfolio, period="perpAllTime")
    dd = drawdown_series(eq)
    assert dd[1] == 0.0
    assert abs(dd[3] - 1.0) < 1e-9


def test_stop_order_rate(raw_orders):
    assert stop_order_rate(raw_orders) == 0.5


def test_ledger_events_typed(raw_ledger):
    evs = ledger_events(raw_ledger)
    assert [e.type for e in evs] == ["deposit", "deposit", "withdraw"]
    assert evs[0].usdc == 19942.95
