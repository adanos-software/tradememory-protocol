"""Full-universe Stage-0 — fetch the complete Hyperliquid leaderboard.

Downloads `stats-data.hyperliquid.xyz/Mainnet/leaderboard` (the full ranked
universe, ~37.8k addresses), archives the raw JSON, and writes EVERY address to
`universe_addrs_full.txt` (one per line). We deliberately keep ALL leaderboard
addresses regardless of their *current* account value: the $25k floor in the
pre-registration is on the **pre-T0 peak**, computed later from each address's
`accountValueHistory`. Pre-filtering on current value would drop exactly the
blown-up masters the study needs (survivorship bias).
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from pathlib import Path

URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
RAW_OUT = Path("research/hyperliquid/leaderboard_raw.json")
ADDR_OUT = Path("research/hyperliquid/universe_addrs_full.txt")


def fetch(max_retry=6):
    delay = 2.0
    last = None
    for attempt in range(max_retry):
        try:
            req = urllib.request.Request(
                URL, headers={"User-Agent": "tm-research/0.1", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read().decode()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"leaderboard fetch failed: {last}")


def main():
    raw = fetch()
    RAW_OUT.write_text(raw, encoding="utf-8")
    data = json.loads(raw)
    rows = data["leaderboardRows"] if isinstance(data, dict) else data
    # Discover the address key (ethAddress on Hyperliquid).
    sample = rows[0]
    addr_key = next(k for k in ("ethAddress", "address", "user", "account")
                    if k in sample)
    addrs = [r[addr_key].lower() for r in rows if r.get(addr_key)]
    # De-dupe, preserve order.
    seen, uniq = set(), []
    for a in addrs:
        if a not in seen:
            seen.add(a)
            uniq.append(a)
    ADDR_OUT.write_text("\n".join(uniq) + "\n", encoding="utf-8")
    print(f"leaderboard rows={len(rows)} unique_addrs={len(uniq)}")
    print(f"row[0] keys={sorted(sample.keys())}")
    print(f"addr_key={addr_key} sample_addr={uniq[0]}")
    print(f"raw bytes={len(raw)}  -> {RAW_OUT}")
    print(f"addrs       -> {ADDR_OUT}")


if __name__ == "__main__":
    main()
