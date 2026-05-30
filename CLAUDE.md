# TradeMemory Protocol — Claude Code 指令

## 專案概述

TradeMemory Protocol 是 Mnemox AI 的核心產品。MT5/forex 交易記憶層，3 層架構（L1 原始交易 → L2 模式發現 → L3 策略調整），MCP server。

- GitHub: mnemox-ai/tradememory-protocol
- PyPI: tradememory-protocol
- 版本: v0.5.1
- Tests: 1293 tests passing (1233 + 60 strategy validator)
- Default branch: `master`（不是 main）

## 開發規範

- Python 3.10+
- 測試：`python -m pytest tests/ -v`（每個任務完成後必須跑，確認沒新增 fail）
- Linting：遵循現有 code style
- Commit message 格式：`type: description`（feat/fix/docs/chore）
- 每完成一個 ROADMAP 任務就 commit + push
- 不要修改核心 MCP tools（src/tradememory/mcp_server.py），除非 ROADMAP 明確要求

## 任務執行流程

1. 開始新 session 時，先讀 docs/ROADMAP.md 確認當前進度
2. 找到第一個未完成（❌）的任務
3. 執行該任務
4. 跑 tests 驗證
5. Commit + push
6. 在 docs/ROADMAP.md 標記 ✅
7. 繼續下一個任務
8. 如果 context 快滿了，先更新 docs/ROADMAP.md 進度，然後結束 session

## 重要文件位置

- MCP tools 定義：`src/tradememory/mcp_server.py`（4 個 MCP tools：store/recall/performance/reflection）
- FastAPI REST server：`src/tradememory/server.py`（35+ REST endpoints）
- MT5 同步：`docs/MT5_SYNC_SETUP.md` + `scripts/mt5_sync.py`
- 每日反思：`scripts/daily_reflection.py`
- Demo：`src/tradememory/demo.py`（`tradememory demo [--fast]`，30 筆模擬交易跑完整 L1→L2→L3 pipeline）
- 測試：`tests/`
- OpenClaw Skill：`.skills/tradememory/SKILL.md`
- 開發路線圖：`docs/ROADMAP.md`
- Scripts 結構：`scripts/`（user-facing）、`scripts/research/`（回測/驗證/遷移）、`scripts/platform/`（.bat/.xml/.sh/.pyw）

## Lessons Learned

- 預設分支是 master 不是 main，所有 GitHub URL 都要用 master
- .env.example 不要放真實憑證
- README 不要用過多 emoji 和行銷語調，保持開發者風格
- 不要承諾還沒實作的功能（Phase 2 不打勾）
- CHANGELOG 要誠實，不要假裝多個 sprint
- Before/After 數據如果是模擬的，要在最上面明確標註
- 刪除的檔案如果曾 commit 過敏感資訊，git 歷史裡還是看得到，要用 filter-branch 清除

## Rules

- 每個任務完成前必須跑 pytest 確認沒壞東西
- commit 前用 git diff 檢查改動範圍是否合理
- 不要一次開太多 MCP tools，會吃 context window
- 寫文件用開發者語調，不要用行銷語調
- 所有模擬數據必須標註 "Simulated"
- 簡單方案優先，不要 over-engineer
- NEVER hardcode credentials. All secrets via `.env` or environment variables
- Use UTC for all timestamps

## Recent Changes (latest 10)
- [2026-05-31] **Plan 2 detector — ALL 8 phases COMPLETE (machinery built; pre-reg Part 2 lock deferred to Plan 3)** — subagent-driven TDD, 18 plan tasks across Phase 0-8, every phase implementer→spec-review→code-review. `research/hyperliquid/detector/`: config / bucketing / James-Stein shrinkage / 9 vol-normalised behavioral primitives / axis compose+sign / per-axis mSPRT (reuses `ssrt/core.py`) / Holm-min-gate+sustained-M composite / 70% guard band / orchestration / label-blind 2-state HMM synthetic generator / calibration grid+pickup / discipline-only ablation. **154 detector tests + main 1474 green** (only `src/` change = `owm/changepoint.py` legacy-CUSUM rename w/ dual-read backward-compat). **4 real bugs caught by review** (size_in_sigma multi-coin / None-equity false-healthy / lda_seed non-determinism / private cross-module import). Demo calibration validates machinery end-to-end (`calibration_result_demo.json`, synthetic anchors → power saturates, NOT a pre-reg number). **Sean approved (2026-05-31) deferring the FINAL Part-2 lock to Plan 3 start** — grid-winner tuple awaits real tuning-split marginals. Next: Plan 3.
- [2026-05-31] **Plan 2 Task 16 DONE** — discipline-only ablation. `config.py`: `mask_axes: frozenset = frozenset()` with subset validation. `sprt_axis.py`: masked axis returns 1.0 immediately, never feeds MixtureSPRT. `hmm_synth.py`: `drift_axes: frozenset | None = None` on SynthSpec, `_mean_vector` shifts only in-set axes (None=all, backward-compat). `ablation.py` (new): `discipline_only_cfg()` + `ablation_sanity()` 3-scenario latency measurement with event-clustered bootstrap CI (B=2000). Sanity bar: ci_low=8.0 > 0, median=8.5, disc_power=1.000 on Scenario A. 154 tests green (+19). HEAD `c2cdb3d`. Branch `copytrading-drift-demo`.
- [2026-05-31] **Plan 2 Tasks 14+15 DONE** — calibration.py: `measure()` (Type-I/power/latency), `lda_weights()` (Fisher LDA per axis, ridge-regularised, fallback to equal), `grid_search()` (bucket×M×tau×weights×kappa, 6h≤M*bucket≤7d constraint), `pick_winner()` (strict 0.02 / relaxed 0.05 type_i, power DESC then M*bucket ASC then dof ASC), `run_calibration()` (full pipeline + JSON artifact: grid_rows, winning_tuple, realized_type_i/power, power_by_delta curve, typeI_target_relaxed). 19 new tests, 135 total green. AST import guard passes. Two commits: `519bd17` (measure) → `HEAD` (grid+artifact). Branch `copytrading-drift-demo`.
- [2026-05-31] **Plan 2 execution — Phase 0+1 DONE** — subagent-driven TDD. Phase 0 (config dataclasses) + Phase 1 (bucketing / James-Stein shrinkage / 9 vol-normalised behavioral primitives across exposure-discipline-tilt). Each task: implementer→spec-review→code-review→fix. **1 real bug caught by spec-review** (size_in_sigma used last fill's coin sigma instead of the largest fill's in multi-coin buckets) + fixed. 56 tests green (`python -m pytest research/hyperliquid/tests/`). HEAD `d1bad19`. Detector front-end done (Trajectory→buckets→9 primitives); next Phase 2 = axis compose + per-axis mSPRT reusing `ssrt/core.py`.
- [2026-05-30] **Plan 2 detector design spec — WRITTEN + reviewer APPROVED** — brainstormed (superpowers) + locked 7 design decisions: hybrid per-fill/bucket-close cadence, grid-searched bucket {1h/4h/24h}, James-Stein shrinkage null (self↔universe), synthetic-MC-tuned per-axis Fisher-LDA weights, 2-state HMM label-blind synthetic generator, in-place legacy binary-CUSUM rename (`owm/changepoint.py`), define+synthetic-sanity ablation (≥50% lead-time bar). Spec `docs/superpowers/specs/2026-05-30-copytrading-drift-detector-design.md` (commit `8f83781` + 4 clarity fixes). spec-document-reviewer **APPROVED** — 4 load-bearing claims verified vs actual code: mSPRT reuse (`ssrt/core.py` signature + one-sided semantics), import-isolation test (`detector/` must not import `owm.*`), CUSUM-rename scope (zero public REST/MCP refs → only src/ change), data-snooping firewall (all tuning on tuning-split only, generator label-blind). 18-task TDD **implementation plan also WRITTEN + plan-reviewer APPROVED** (reviewer ran the real MixtureSPRT to verify API + pytest 23-green + grep scope) `docs/superpowers/plans/2026-05-30-copytrading-drift-detector.md` (commit `3cacf7e` + clarity fixes). Awaiting Sean's go to execute (subagent-driven vs inline).
- [2026-05-30] **Copy-trading blow-up paper pivot** — reframed the self-monitoring CUSUM paper into a flagship: detect master-trader behavioral drift on real Hyperliquid on-chain data BEFORE blow-ups harm followers. Hyperliquid API feasibility = GO (spike archived `research/hyperliquid/SPIKE-2026-05-30.md`: `liquidation` key on fills, equity crater, trigger orders, margin-topup ledger all retrievable). Design spec `docs/superpowers/specs/2026-05-30-copytrading-drift-paper-design.md` (rev2, passed 2 adversarial reviews → APPROVED-WITH-MINORS). Headline=lead-time over non-trivial early baselines; frozen-at-T0 cohort (kills survivorship bias); guard-band vs label leakage; event-clustered stats. Recycles MaxDDStop/BOCPD/DQS as motivation+negatives. Branch `copytrading-drift-demo`. **Plan 1 Tasks 1-8 built `research/hyperliquid/` (23 tests green, HEAD `d298018`). Task 9 viability = GO (`research/hyperliquid/COHORT-REPORT.md`): 37,872-addr leaderboard, 300-sample 89% raw blow-up BUT 66% on one market-crash day (2026-01-07) → real gold = ~38-53 idiosyncratic blow-ups across ~22 independent days. Headline cohort LOCKED = idiosyncratic lead-time (A) + crash-day discrimination (B). Next: lock pre-reg params → Plan 2 detector.**
- [2026-04-10] **SSRT Phase 2** — shift_null (preserve evidence on regime change) + tau sweep (0.3/0.5/1.0). 22,500 MC runs. Key findings: shift_null WORSE than reset (50.2% vs 57.0% det rate on regime_specific); tau=0.3 is best (+5pp power, Type I=0.008); mSPRT_t03 = best statistically-valid method (81.4% power, only method with Type I < 0.05). Regime-aware approaches both fail — fixed null dominates.
- [2026-04-10] **SSRT Phase 1** — mSPRT engine (Johari et al.) + regime-aware null + 15k Monte Carlo experiments. mSPRT Type I=0.012 (only method < 0.05). Regime-aware null worse than fixed null (evidence loss on reset). 14 new tests, 12 files.
- [2026-04-10] **arXiv paper major revision** — 6300 words, 17 refs. MaxDDStop (equity DD threshold) outperforms CUSUM 93.5%. Reframed CUSUM as diagnostic tool. Added k=0 justification, robustness check (without BTCUSDT 1h: vs SimpleWR p=0.179), strategy dependence caveat. h sensitivity pending.
- [2026-04-10] **Level 2 PASS** — CUSUM validated: 200 strategies × 6 agents, 73.5% win rate vs baseline, d=0.76, p≈0, bootstrap CI [+3180, +4560], 4/4 gates pass. BUT MaxDDStop beats CUSUM 93.5% on DD reduction.
- [2026-04-10] **Level 0+1** — BOCPD: DEAD（sparse binary 不適合）, CUSUM: ALIVE, DQS: DEAD
- [2026-04-10] **Research framework** — 4-level validation protocol (L0 component → L1 controlled → L2 multi-strategy → L3 multi-market)
- [2026-04-09] Phase 4b fixes — warm-start, equity metrics, adaptive DQS thresholds, CUSUM adaptive target_wr
- [2026-04-09] Phase 3 — Simulation Framework: BaseAgent/CalibratedAgent, ABExperiment, ablation, 3 presets
- [2026-04-09] Phase 1+2 — BOCPD + DQS modules (later found DQS dead, BOCPD dead)
- [2026-04-08] **深度重構 — 審計行動計劃全部完成**：
  - Phase A: 刪除 store_trade_memory + recall_similar_trades（19→17 tools），修正行銷語言，加 Research Status
  - Phase B: 記憶層互通 — Semantic 讀 Episodic（drift detection >15%），Procedural 補完（hold time, Kelly, disposition），Affective 讀 Procedural（behavioral risk adjustment）
  - Phase C: db.py 錯誤處理改 raise TradeMemoryDBError（18→2 個 return False），加 get_connection context manager
  - Phase D: 12 property-based tests (hypothesis) + 5 integration tests（no mocks）
  - Phase E: 4 ADR + OWM 技術文章草稿

## Current Status
- **Copy-trading drift paper**: **Plan 2 COMPLETE — all 8 phases (2026-05-31)**. Full detector machinery in `research/hyperliquid/detector/` (pipeline → HMM synthetic generator → calibration grid → discipline-only ablation → legacy-CUSUM rename), **154 detector tests + main 1474 green**, every phase implementer→spec-review→code-review. Demo calibration validates machinery end-to-end (`research/hyperliquid/detector/calibration_result_demo.json`). **pre-reg Part 2 lock DEFERRED to Plan 3 start (Sean approved 2026-05-31)** — final grid-winner (bucket/M/τ/weights/κ) tuple awaits real tuning-split marginals (40% split, outcome-blind, no locked-test contact), not synthetic placeholders. Pre-reg Part 1 LOCKED (`92e343c`). Final whole-implementation review = **SHIP-READY, firewall PASS**; logged 3 Plan-3 pre-lock items in pre-reg Part 2 (SNR δ/1.4826 scaling align-or-document; κ is an INERT knob under synthetic self==universe — needs real distinct self/universe; add self≠universe integration test). **Next: Plan 3 — compute tuning-split → lock Part 2 → real-cohort experiments (Claim A lead-time / B discrimination / C impact-frame) → paper → Monday-listing arXiv.** Branch `copytrading-drift-demo`.
- **v0.5.1** — PyPI + GitHub Release 已發（2026-03-27）
- **1374 tests passing** (1253 + 60 strategy validator + 11 legitimacy + 12 property-based + 5 integration + 10 DQS + 8 changepoint + 10 simulation + 14 SSRT - 9 removed), 1 failed (anthropic SDK), 1 skipped
- **SSRT Module**: `src/tradememory/ssrt/` — mSPRT engine (tau=0.3 default), shift_null, regime-aware null, simulator, baselines. Phase 1+2 results in `validation/ssrt/`. Best method: mSPRT_t03 (81.4% power, Type I=0.008). Regime-aware approaches both fail.
- **18 MCP tools** (+compute_dqs), 35+ REST endpoints
- **Phase 5 Rigorous Validation Complete**: 100 experiments (2 symbols × 1h × 50 grid strategies × 5 agents)
  - Result: **INVALID** — CalibratedAgent skips 97% trades (48/100 zero-trade), DD "reduction" from NOT TRADING
  - DQS skip tier too aggressive on cold-start DB, BOCPD changepoint effect unmeasurable
  - 0/100 DSR PASS, sensitivity sweep: all 10 hazard_rates identical (0.9883 reduction)
  - New: `strategy_generator.py` (189 grid strategies), `baselines.py` (3 naive agents)
  - Report: `scripts/research/phase5_results.md`
- **Phase 4**: 12 A/B + 48 ablation, NO-GO, 6/12 DSR PASS. Report: `scripts/research/phase4_results.md`
- **Agent Simulation Framework**: BaseAgent vs CalibratedAgent A/B + 3 naive baselines, IS/OOS walk-forward, 4-variant ablation, grid + preset strategies
- **Bayesian Changepoint Detection**: BOCPD + CUSUM complementary detector, 4 behavioral signals, DB-persisted, cusum_alert in ChangePointResult
- **DQS Engine**: 5 continuous factors + 4-tier system (go/proceed/caution/skip) + calibrate() + integrated into remember_trade
- **5 層記憶真正互通**：Semantic↔Episodic（drift detection → BOCPD），Procedural（hold time/Kelly/disposition），Affective←Procedural（behavioral risk）
- **db.py 重構**：TradeMemoryDBError 階層 + get_connection() context manager + 18→2 return False
- **4 ADR** in docs/adr/ — OWM scoring, SQLite, MCP protocol, Evolution gates
- **OWM 技術文章**草稿 in docs/research/owm-technical-article.md
- **Strategy Validator 三層完成**：L1 MCP Tool + L2 Claude Code Skill + L3 Web UI (mnemox.ai/validate)
- **PR #2 open** — ElishaKay: Fronteir AI hosted deployment link（外部貢獻，待 review）
- **Uncommitted** — `scripts/mt5_sync_v3.py` close retry 邏輯
- **CHANGELOG** — 停在 v0.5.0，v0.5.1 section 未寫
- **Waiting on**: NG_Gold demo 交易數據、anti-resonance PyPI publish
- **方向**: Trading AI Service 接案→數據驗證→SaaS
- **行銷啟動（2026-04-05）**：README CTA、Reddit 草稿、Demo Video 腳本、Awesome-list 指南

## Compact Instructions

When compacting, preserve: docs/ROADMAP.md progress, key design decisions (LLM validation, UTC enforcement, platform-agnostic core), current task progress, security rules, lessons learned, rules.
