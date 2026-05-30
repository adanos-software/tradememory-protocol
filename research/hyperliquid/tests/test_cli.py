import json
from research.hyperliquid.__main__ import run


def test_cli_emits_manifest(tmp_path, fake_transport_cls, raw_fills, raw_portfolio, raw_ledger, raw_orders):
    addrs = tmp_path / "addrs.txt"
    addrs.write_text("0xabc\n")
    ft = fake_transport_cls([
        (lambda b: b["type"] == "userFillsByTime", raw_fills),
        (lambda b: b["type"] == "portfolio", raw_portfolio),
        (lambda b: b["type"] == "historicalOrders", raw_orders),
        (lambda b: b["type"] == "userNonFundingLedgerUpdates", raw_ledger),
    ])
    out = tmp_path / "cohort.json"
    man = run(addrs_path=str(addrs), t0_ms=1, window_end_ms=10**13,
              out_path=str(out), transport=ft, archive_dir=str(tmp_path / "arch"),
              dd_pct=0.5, recovery_frac=0.8, recovery_horizon_ms=86_400_000,
              min_trades=1, min_days=0.0)
    saved = json.loads(out.read_text())
    assert "base_rate" in saved and "effective_n_events" in saved
    assert saved["t0_ms"] == 1
