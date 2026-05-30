import json
from pathlib import Path
from research.hyperliquid.client import HyperliquidClient


def test_post_archives_raw_response(tmp_path, fake_transport_cls):
    ft = fake_transport_cls([(lambda b: b["type"] == "portfolio", {"ok": 1})])
    c = HyperliquidClient(transport=ft, archive_dir=tmp_path, rate_delay_s=0)
    out = c.post({"type": "portfolio", "user": "0xabc"})
    assert out == {"ok": 1}
    files = list(Path(tmp_path).rglob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text())
    assert saved["request"]["type"] == "portfolio"
    assert saved["response"] == {"ok": 1}
    assert "query_time_ms" in saved


def test_fetch_user_fills_paginates_and_dedupes(tmp_path, fake_transport_cls):
    page1 = [{"tid": i, "time": 1000 + i} for i in range(2000)]
    page2 = [{"tid": 1999, "time": 2999}] + [{"tid": i, "time": 3000 + i} for i in range(2000, 2005)]

    def resp(body):
        return page1 if body["startTime"] <= 1000 else page2

    ft = fake_transport_cls(side_effect=resp)
    c = HyperliquidClient(transport=ft, archive_dir=tmp_path, rate_delay_s=0)
    fills = c.fetch_user_fills_by_time("0xabc", start_ms=1000, max_pages=3)
    tids = [f["tid"] for f in fills]
    assert len(tids) == len(set(tids))
    assert tids.count(1999) == 1
    assert len(fills) == 2005
    assert c.last_fetch_truncated is False
