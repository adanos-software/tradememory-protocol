# Phase 5 — Indicative Experiment Results (2026-05-31)

> ⑤「笨方法對照 + 完整實驗」一次做完。SCALED / PROVISIONAL / INDICATIVE — NOT the pre-reg locked-test read.
> Cohort: 199 real masters (95 blowup / 104 stable), default cfg (NOT calibrated), held-out test+val.

## TL;DR（誠實版）

**實驗 harness 完整建好了**（early-window baseline + B1/B2/B3 baselines + Claim A/B/ablation with event-clustered bootstrap, 49 tests）。在真實資料上跑出 indicative 結果 —— 而結果是**負面的**：

- **Claim A FAIL**: 偵測器 lead 比最強笨方法**慢** 154h（median advantage −154h, 95% CI [−437, 0]）。
- **Claim B FAIL**: 偵測率僅 14%（63 爆倉只 9 個 early-fire），AUC 0.586（CI-low 0.510 < 0.65 gate）。但 fire 的精準（PPV 0.75, FPR 0.048）。
- **Ablation**: 偵測器在多數爆倉 0 lead，無法評估。

**這是 no-data-snooping 原則的價值**：我們在發論文前誠實看到「目前偵測器贏不了笨方法」，而不是在 test 上調到好看再鎖定。**結論：現在絕不該鎖定 ⑥ + 發論文。**

## 診斷（tuning split，不碰 test 調參）— 4 個根因

1. **Stability guard 排除 47% 爆倉**：32 個 tuning 爆倉，15 個被 early-window 穩定期保護排除（一進觀察期就在 drift → 沒乾淨基準）。這是「early-window baseline」方案的真實代價，比預期嚴重。
2. **偵測器 default cfg 太保守**：非排除的 17 個只 2 個 early-fire（12%）。M=3 + James-Stein shrinkage（kappa=14）+ guard band 三重壓制。cfg 未在真實資料校準。
3. **笨方法 baseline 實作太鬆 → Claim A 比較不公平**：B2 dd-velocity median lead 3694h（≈153 天）、B3 806h（≈34 天）。這麼長的「lead」= baseline 幾乎一進場就 fire（near-always-fire），不是「非平凡 early warning」。對 always-fire baseline 比 lead-time 本來就不公平 —— 偵測器永遠輸，但 always-fire baseline 無用（沒測它們在 stable master 的 FPR）。
4. **Guard band killer**：11/32 爆倉的第一筆強平在最早 20% → pre-first-liq guard band 把 alert window 掐到極短。

## Plan 3 正式 run 前的 must-fix（這些是真實 blocker）

A. **重新設計 baseline 比較**：B1/B2/B3 必須在 stable master 上 FPR 受控（非 always-fire），再比 lead；或把 Claim A 改成「FPR-matched lead」。否則 lead-time 比較無意義。
B. **Stability guard 放寬 / 重想**：47% 排除率太高。要嘛放寬 healthy 門檻，要嘛接受「一進場就 drift」的 master 用不同處理（他們其實是最該抓的）。
C. **偵測器正式校準**：default cfg 沒調。要在 synthetic（用真實 tuning anchors）跑 calibration → winner cfg，再上真實資料。但校準優化的是 synthetic detection，不保證 real lead vs baseline — 可能要重想 detector 靈敏度/guard band。
D. **Guard band 對 early-liq 爆倉**：first_liq 太早的 master 需要不同的 early-window 定義。

## 檔案
- harness: `research/hyperliquid/experiments/`（series_runner / early_baseline / baselines / experiment）
- runner: `research/hyperliquid/experiment_run.py`
- results: `research/hyperliquid/plan3_experiment_results.json`
- cohort: `research/hyperliquid/cohort_behavioral.json`（199 masters）

## 為什麼這是好消息

論文的 reframe 核心張力就是「笨方法（看得到 equity）會贏 behavioral detector」。我們的 thesis 是「follower 看不到 master equity，所以需要 behavioral lead」。但 indicative 結果說：**在這個 cohort + 這個 detector/baseline 設計下，behavioral mSPRT 連贏這些早期 tripwire 都做不到**。在投稿前知道這個，比被審稿人打臉好太多。Plan 3 的價值就是把 A–D 解掉，再誠實重跑 —— 如果解完還是輸，那是論文要面對的真相；如果解完贏，那才是站得住的 headline。
