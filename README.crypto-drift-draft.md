<!-- mcp-name: io.github.mnemox-ai/tradememory-protocol -->
<!-- ============================================================= -->
<!-- DRAFT — crypto copy-trading drift repositioning (2026-05-28)  -->
<!-- DO NOT push to live README.md until the broker drift demo     -->
<!-- exists behind it. Use this framing with Edison/OTSO first.    -->
<!-- ============================================================= -->

<p align="center">
  <img src="assets/header.png" alt="TradeMemory Protocol" width="600">
</p>

<div align="center">

[![PyPI](https://img.shields.io/pypi/v/tradememory-protocol?style=flat-square&color=blue)](https://pypi.org/project/tradememory-protocol/)
[![Tests](https://img.shields.io/badge/tests-1%2C428_passed-brightgreen?style=flat-square)](https://github.com/mnemox-ai/tradememory-protocol/actions)
[![MCP Tools](https://img.shields.io/badge/MCP_tools-20-blueviolet?style=flat-square)](https://smithery.ai/server/io.github.mnemox-ai/tradememory-protocol)
[![Smithery](https://img.shields.io/badge/Smithery-listed-orange?style=flat-square)](https://smithery.ai/server/io.github.mnemox-ai/tradememory-protocol)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)

[Getting Started](docs/GETTING_STARTED.md) | [Use Cases](docs/USE_CASES.md) | [API Reference](docs/API.md) | [OWM Framework](docs/OWM_FRAMEWORK.md) | [Limitations](LIMITATIONS.md) | [中文版](docs/README_ZH.md)

</div>

---

**Copy traders don't blow up because the master was bad. They blow up because the master *drifted* — and the leaderboard never showed it.**

A master trader posts 90 days of clean returns. Followers pile in. Then the behavior quietly changes — bigger size, stops removed, revenge trades after a red day. The performance curve still looks green. The blow-up lands 30 days later, and every follower goes down with it.

ZuluTrade solved this for forex 14 years ago with ZuluGuard: auto-flag signal providers whose behavior deviates from their norm. But it's locked inside one platform, it's a black box, and it never came to crypto.

**TradeMemory is the open, vendor-neutral behavioral-drift layer for copy trading.** It builds a behavioral fingerprint for every master trader, detects when they drift from their own baseline, and emits a `stable / warning / broken` signal — with a tamper-proof audit trail behind every call. Crypto-native. Transparent. `pip install`.

## The problem, in one line

> Followers don't lose to bad traders. They lose to **good traders who quietly stopped being themselves.**

- Leaderboards rank on recent P&L — the worst possible signal (selection bias toward hot streaks about to revert)
- A master's risk personality drifts long before the equity curve breaks
- Platforms see the churn *after* the blow-up, never before
- Regulators are circling: [IOSCO FR/06/2025](https://www.iosco.org/library/pubdocs/pdf/IOSCOPD793.pdf) on copy trading, FCA finfluencer warnings, CFTC prop-firm scrutiny

## What TradeMemory does

- **Fingerprint** — builds a behavioral signature per trader: holding time, position sizing, trade frequency, win/loss-streak response, MAE/MFE, revenge-trading, session bias, risk escalation
- **Detect drift** — compares each trader's recent window against their *own* baseline and emits `stable / warning / broken`, naming the exact factors that moved
- **Explain** — every signal carries the reasoning trace and the memories behind it, not just a number
- **Audit** — every decision is SHA-256 hashed into a forward-chained ledger; tamper with one record and every later link breaks

Works on any market (crypto, forex, equities, futures), any broker, any AI platform. TradeMemory never executes trades or touches funds — it records, fingerprints, and scores.

## Who it's for

| | Copy-trading platform / broker | AI trading agent / EA | Quant / prop desk |
|---|---|---|---|
| **Problem** | Master traders drift, followers blow up, the brand takes the hit | Agent repeats mistakes, can't explain trades, forgets across sessions | Strategy edge decays silently |
| **TradeMemory gives** | Per-master drift score + behavioral fingerprint + audit trail | Outcome-weighted memory + pre-trade gate + decision log | Behavioral-drift + anti-resonance signal-decay detection |
| **Surface** | `/score` API + risk dossier | MCP tools + REST | REST + reflections |

## Why not just use…

| | ZuluGuard (ZuluTrade) | eToro Risk Score | **TradeMemory** |
|---|---|---|---|
| Detects behavioral drift | Yes | No (static 1–10) | **Yes** |
| Vendor-neutral (any platform) | No (ZuluTrade only) | No (eToro only) | **Yes** |
| Crypto-native | No (forex) | Limited | **Yes** |
| Transparent / open algorithm | No (black box) | No | **Yes — MIT, auditable** |
| Tamper-proof audit trail | No | No | **Yes — SHA-256 chain** |
| Reasoning trace, not just a score | No | No | **Yes** |

> ZuluGuard proved platforms want this. TradeMemory makes it open, crypto-native, and something *any* platform can integrate — not a feature locked inside one broker.

## Quick Start

```bash
pip install tradememory-protocol
```

Add to Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "tradememory": {
      "command": "uvx",
      "args": ["tradememory-protocol"]
    }
  }
}
```

Then tell Claude: *"Record my AAPL long at $195 — earnings beat, institutional buying, high confidence."*

<details>
<summary>Claude Code / Cursor / Docker</summary>

```bash
# Claude Code
claude mcp add tradememory -- uvx tradememory-protocol

# From source
git clone https://github.com/mnemox-ai/tradememory-protocol.git
cd tradememory-protocol && pip install -e . && python -m tradememory

# Docker
docker compose up -d
```

</details>

**Full walkthrough:** [Getting Started](docs/GETTING_STARTED.md)

## How it works

<p align="center">
  <img src="assets/owm-factors.png" alt="OWM 5 Factors" width="900">
</p>

1. **Record** — every trade (and every decision *not* to trade) writes to five memory layers: episodic, semantic, procedural, affective, and trade records
2. **Fingerprint** — the procedural + affective layers compose into a behavioral signature: how this trader sizes, holds, recovers from losses, escalates risk
3. **Detect drift** — recent-window behavior is compared against the trader's own baseline; significant deviation emits `stable / warning / broken` with the factors that moved
4. **Audit** — every record is SHA-256 hashed at creation and linked into a forward-chained ledger; daily Merkle roots anchor the chain (RFC 3161 TSA in progress)

### MCP Tools

| Category | Tools | Description |
|----------|-------|-------------|
| **Memory** | `remember_trade` · `recall_memories` | Record and recall trades with outcome-weighted scoring |
| **Behavioral** | `get_agent_state` · `get_behavioral_analysis` | Confidence, drawdown, streaks, drift detection |
| **Planning** | `create_trading_plan` · `check_active_plans` | Prospective plans with conditional triggers |
| **Risk** | `check_trade_legitimacy` | 5-factor pre-trade gate (full / reduced / skip) |
| **Audit** | `export_audit_trail` · `verify_audit_hash` | SHA-256 tamper detection + bulk export |

<details>
<summary>All 17 MCP tools + REST API</summary>

| Category | Tools |
|----------|-------|
| **Core Memory** | `get_strategy_performance` · `get_trade_reflection` |
| **OWM Cognitive** | `remember_trade` · `recall_memories` · `get_behavioral_analysis` · `get_agent_state` · `create_trading_plan` · `check_active_plans` |
| **Risk & Governance** | `check_trade_legitimacy` · `validate_strategy` |
| **Evolution** | `evolution_fetch_market_data` · `evolution_discover_patterns` · `evolution_run_backtest` · `evolution_evolve_strategy` · `evolution_get_log` |
| **Audit** | `export_audit_trail` · `verify_audit_hash` |

**REST API:** 35+ endpoints for trade recording, reflections, risk, MT5 sync, OWM, evolution, and audit. [Full reference →](docs/API.md)

</details>

## Behavioral audit trail

Every decision — including decisions **not** to trade — is recorded as a Trading Decision Record (TDR). Per-record SHA-256 content hashes are linked into a forward-chained ledger; every UTC day is summarised by a Merkle root which itself chains across days. Tampering with any historical record invalidates every subsequent link.

```bash
# Score a trader's drift status from their trade history
POST /score  { "trades": [...] }
# → {"status": "warning", "drifted_factors": ["position_sizing", "revenge_trading"], "hash": "a05544..."}

# Verify a single record hasn't been tampered with
verify_audit_hash(trade_id="MT5-7047640363")
# → {"verified": true, "chain_entry": {"sequence_num": 42, ...}}

# Daily Merkle root — single 32-byte anchor over every TDR for that day
get_daily_root(date="2026-05-14")
# → {"verified": true, "root_hash": "a05544...", "record_count": 18}
```

The same audit chain that proves a master trader's drift score wasn't fabricated also satisfies algorithmic-decision-documentation requirements ([MiFID II Art. 17](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32014L0065), [EU AI Act Art. 12/14](https://eur-lex.europa.eu/eli/reg/2024/1689)) for platforms that need it. See [LIMITATIONS.md](LIMITATIONS.md) for the full maturity statement.

## Security

- **Never touches API keys.** TradeMemory does not execute trades, move funds, or access wallets.
- **Read and record only.** Your platform passes trade history to TradeMemory. It fingerprints and scores. That's it.
- **Runs locally / self-hosted.** No data sent to third parties in the open-source build.
- **SHA-256 chained audit ledger.** Every record hashed at creation and linked to the previous; daily Merkle roots anchor the chain.
- **1,428 tests passing.** Full test suite with CI.

## Pricing

| | Community | Platform | Enterprise |
|---|---|---|---|
| **Price** | **Free** | **Usage-based** (pilot) | **Contact Us** |
| Core MCP tools | 17 tools | 17 tools | 17 tools |
| Drift `/score` API | self-hosted | hosted | private deployment |
| Behavioral dashboard | — | per-trader risk dossier | custom |
| Audit / compliance export | included | included | reports + SLA |
| Support | GitHub Issues | Priority | Dedicated |
| | [Get Started →](docs/GETTING_STARTED.md) | *pilot — [contact](mailto:dev@mnemox.ai)* | [dev@mnemox.ai](mailto:dev@mnemox.ai) |

### Running a copy-trading platform?

If you operate copy trading or signal-provider products and want to surface master-trader drift to your followers before the blow-up, we run design-partner pilots.

**Free 30-min call** — bring 5–10 anonymized master accounts and we'll show you a live drift dossier on your own data.

[dev@mnemox.ai](mailto:dev@mnemox.ai) | [Book a call](https://calendly.com/johnson90207/30min)

## Research Status

TradeMemory's OWM framework is grounded in cognitive science (Tulving 1972) and reinforcement learning (Schaul et al. 2015). Current status:

- **OWM five-factor scoring:** implemented, tested (1,300+ tests)
- **Behavioral drift detection:** baseline-vs-recent window comparison (CUSUM); behavioral-signature extraction implemented
- **Statistical validation:** DSR, MBL implemented (Bailey-de Prado 2014)
- **Audit trail:** SHA-256 tamper-proof TDR + daily Merkle roots
- **Empirical validation:** ongoing (target n≥100 for statistical significance)

## Documentation

| Doc | Description |
|-----|-------------|
| [Getting Started](docs/GETTING_STARTED.md) | Install → first trade → first drift score |
| [Use Cases](docs/USE_CASES.md) | Real-world production scenarios |
| [API Reference](docs/API.md) | All REST endpoints |
| [OWM Framework](docs/OWM_FRAMEWORK.md) | Outcome-Weighted Memory theory |
| [Architecture](docs/ARCHITECTURE.md) | System design & layer separation |
| [MT5 Setup](docs/MT5_SYNC_SETUP.md) | MetaTrader 5 integration |
| [Failure Taxonomy](docs/trading-ai-failure-taxonomy.md) | 11 trading AI failure modes |
| [中文版](docs/README_ZH.md) | Traditional Chinese |

## Contributing

See [Contributing Guide](.github/CONTRIBUTING.md) · [Security Policy](.github/SECURITY.md)

<a href="https://star-history.com/#mnemox-ai/tradememory-protocol&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=mnemox-ai/tradememory-protocol&type=Date&theme=dark" />
   <img alt="Star History" src="https://api.star-history.com/svg?repos=mnemox-ai/tradememory-protocol&type=Date" width="600" />
 </picture>
</a>

---

MIT — see [LICENSE](LICENSE). For educational/research purposes only. Not financial advice.

<div align="center">Built by <a href="https://mnemox.ai">Mnemox</a></div>
