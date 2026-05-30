# Morning Brief — TradeMemory Copy-Trading Drift Paper (2026-05-31, 通宵自動跑)

> 給 Sean 早上掃。Branch `copytrading-drift-demo`，全部 commit 已 push。

## TL;DR（30 秒）

- **Plan 2（偵測器 machinery）100% 完成**：8 phases TDD，每個 implementer→spec-review→code-review，154 detector tests + 主 1474 tests 全綠，整體 final review = **SHIP-READY + data-snooping firewall PASS**。
- **真實 Hyperliquid cohort 撈好了**（scaled 1206 master，pre-reg T0=2025-06-01）：**443 個 idiosyncratic 爆倉 + 49 個獨立 crash events** — 比 viability 強 8 倍，Claim A 的統計基礎很穩。
- **偵測器在真實爆倉 master 上 demo 成功**：3/6 fire，提前 **~20 天**（median 492h）偵測到 exposure（槓桿）drift。indicative、非 pre-reg 方法，但證明 machinery + 偵測能力在真實資料上成立。
- **真實資料揭露 3 個 Plan 3 必修點**（見下），這些是 full-run 前一定要解的坑，現在先撞出來＝省下未來踩雷。
- **沒有按任何不可逆的鍵**：pre-reg Part 2 lock / locked-test 讀取 / arXiv 提交全留給你。

## Plan 2 — 完成（machinery）

`research/hyperliquid/detector/`：config / bucketing / James-Stein shrinkage / 9 vol-normalized 行為 primitives / axis compose+sign / per-axis mSPRT（重用 `ssrt/core.py`）/ Holm-min-gate+sustained-M composite / 70% guard band / orchestration / label-blind 2-state HMM 合成生成器 / calibration grid+pickup / discipline-only ablation。Review 一路攔下 6 個真 bug。Demo calibration（synthetic）端到端驗證 machinery。

## 真實 cohort（Stage 1，equity-only labeling，`cohort_stage1.json`）

| 指標 | 值 |
|---|---|
| sample / labeled | 1206 / 1206（0 error）|
| base rate | 57%（685 爆 / 521 穩）|
| **idiosyncratic 爆倉** | **443**（行為驅動，非市場崩盤日）|
| **獨立 crash events（effective-N）** | **49** |
| market-event days（τ=3% 自動標）| 2025-06-04（190 爆）、06-11（52）|

意義：pre-reg T0=2025-06-01 的 cohort 充足且抗 selection bias，443 idiosyncratic + 49 events 足以撐 Claim A 的 event-clustered 統計。

## 偵測器在真實資料上（indicative smoke）

frozen 偵測器跑 6 個真實 idiosyncratic 爆倉 master（in-window self-baseline）：**3/6 fire，carrying axis 全是 exposure（槓桿），median lead ≈ 492h（~20 天）**。證明偵測器在真實 trajectory 上 run-able 且真的抓到爆前的槓桿 drift。⚠️ 這不是 pre-reg 數字（baseline 用觀察窗內早期而非 pre-T0；self==universe；沒跟 B1/B2/B3 比）。

## ⚠️ 真實資料揭露的 3 個 Plan 3 必修點

1. **Sparse-primitive normalization**：count/rate primitives（topup_count、loser_add_count…）在真實 master 大多 = 0 → MAD=0 → 原本的 1e-6 floor 讓 z-score 爆炸 → type_i≈1。已用 std-based robust scale 暫修；Plan 3 要正式決定 sparse primitive 的 normalization（log1p / rate-transform / z-clip）。
2. **10k-fill-cap × T0=2025-06-01 → behavioral baseline 幾乎不可得**：high-freq master 的 fills 撞 10k cap，撈不到 2025-06-01 之前的歷史 → `meets_baseline`（≥50 pre-T0 fills）幾乎全 fail（140 撈 0 included）。這是 pre-reg #8 disclosed selection bias 的**實務嚴重版**。Plan 3 要決策：(a) 更近的 T0、(b) early-window baseline、(c) equity-derived behavioral proxies、(d) 接受偏 low-freq cohort。**這個要你拍板，影響 pre-reg。**
3. **Nested order structure**：真實 `historicalOrders` 是 `{"order": {...}, "status"}` nested，mock 是 flat。已修 `order_events`（相容兩者），154 tests 仍綠。

## 留給你的不可逆 / 需帳號的步驟（我沒碰）

- **full-universe pre-reg run**（37,879 addr，~12h + 嚴格按 pre-reg 順序）
- **pre-reg Part 2 lock**（timestamped commit，一旦讀 locked test 就定了）
- **locked-test 讀取 + Claim A/B/C 最終統計**
- **arXiv 提交**（你的帳號 + 週一 listing 時機）

## Next（Plan 3，計畫在 `docs/superpowers/plans/2026-05-31-plan3-real-cohort-experiments.md`）

先解上面 3 個必修點（尤其 #2 要你決策 baseline 方法）→ build B1/B2/B3 baselines + experiment harness → tuning-split calibration → **你拍板鎖 Part 2** → locked-test 跑 A/B/C → 論文 → arXiv。

## 檔案索引

- 真實 cohort：`research/hyperliquid/cohort_stage1.json`
- Stage 1/2 driver：`research/hyperliquid/stage1_label.py` / `stage2_behavioral.py`
- Plan 2 spec/plan：`docs/superpowers/specs/2026-05-30-copytrading-drift-detector-design.md` / `plans/2026-05-30-copytrading-drift-detector.md`
- Plan 3 plan：`docs/superpowers/plans/2026-05-31-plan3-real-cohort-experiments.md`
- Pre-reg（Part 1 locked, Part 2 + 必修 checklist）：`research/hyperliquid/PRE-REGISTRATION-DRAFT.md`
- 偵測器 package：`research/hyperliquid/detector/`（154 tests：`python -m pytest research/hyperliquid/tests/`）
