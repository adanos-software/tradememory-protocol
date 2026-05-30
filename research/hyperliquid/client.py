from __future__ import annotations
import json
import time
import urllib.request
from pathlib import Path

API = "https://api.hyperliquid.xyz/info"


def _default_transport(body):
    req = urllib.request.Request(
        API, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "tm-research/0.1"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())


class HyperliquidClient:
    def __init__(self, transport=None, archive_dir="research/hyperliquid/_archive",
                 rate_delay_s=0.3, clock=lambda: int(time.time() * 1000)):
        self._transport = transport or _default_transport
        self._archive = Path(archive_dir)
        self._rate_delay_s = rate_delay_s
        self._clock = clock
        self._archive_seq = 0
        self.last_fetch_truncated = False

    def post(self, body):
        resp = self._transport(body)
        self._archive_raw(body, resp)
        return resp

    def _archive_raw(self, body, resp):
        user = body.get("user", "global")
        d = self._archive / user
        d.mkdir(parents=True, exist_ok=True)
        ts = self._clock()
        self._archive_seq += 1  # avoid same-ms overwrite during pagination
        path = d / f"{body['type']}_{ts}_{self._archive_seq}.json"
        path.write_text(json.dumps(
            {"query_time_ms": ts, "request": body, "response": resp}))

    def fetch_user_fills_by_time(self, user, start_ms, end_ms=None, max_pages=6):
        """Paginate userFillsByTime (<=2000/page, <=10k available). Dedupe by tid.
        Sets self.last_fetch_truncated=True iff the page cap was hit with a still-full
        last page (more history exists than fetched - the 10k-cap selection-bias proxy)."""
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
                self.last_fetch_truncated = True
            cur = max(f["time"] for f in batch) + 1
            time.sleep(self._rate_delay_s)
        return out

    def fetch_portfolio(self, user):
        return self.post({"type": "portfolio", "user": user})

    def fetch_historical_orders(self, user):
        return self.post({"type": "historicalOrders", "user": user})

    def fetch_ledger(self, user, start_ms):
        return self.post({"type": "userNonFundingLedgerUpdates",
                          "user": user, "startTime": start_ms})
