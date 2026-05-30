def test_package_imports():
    import research.hyperliquid  # noqa: F401


def test_fixtures_load(raw_fills, raw_portfolio, raw_ledger, raw_orders):
    assert raw_fills[1]["liquidation"]["method"] == "market"
    assert raw_portfolio[0][0] == "perpAllTime"
