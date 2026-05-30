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
    NOTE: dispatch lives in __call__ on the CLASS - never monkeypatch ft.__call__ on an
    instance (Python looks up dunders on the type, so an instance attr is ignored)."""
    def __init__(self, responses=None, side_effect=None):
        self._responses = list(responses or [])
        self._side_effect = side_effect
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
