# Copy-Trading Pivot — RESUME (2026-05-28)

> 筆電接手用。這個 session 把 TradeMemory 戰略 pivot 想清楚 + 過了 3 輪審查 + 完成 2 個交付。
> 完整決策記錄在 memory: `tradememory-crypto-drift-pivot-2026-05-28.md`（claude-config repo 同步）

## 一句話決策（LOCKED）

TradeMemory 重新定位 = **Copy-Trading Suitability Monitor** — 「在 master 拖垮 follower 之前凍結跟單流入」。給 crypto copy-trading broker（OTSO / BTSE / Bitget / Bybit）的 behavioral-drift / risk-intelligence layer。定位 = 「ZuluGuard for crypto，但 vendor-neutral + 透明 + SHA-256 審計」。

**不做**：retail、HFT、compliance framing、horizontal memory race（Mem0/XMem）。

## 3 輪審查結論（都過）

1. **office-hours（6 forcing questions）**：揭穿原本「TradeMemory 要不要 productize」是錯問題；真議題是「打哪個市場」。
2. **codex 審查**（讀了真 code）：GO-WITH-CHANGES。抓到 3 個 bug — 多重比較誤報(8 factor→33.7%)、label leakage、MaxDDStop 是 baseline(賣 lead-time 不賣降 DD)。給了 reframe「Master Risk Early-Warning + Audit Packet」。
3. **Opus 4.7 審查**（讀了真 code）：SHIP-WITH-CHANGES。找到 codex 漏的 — **follower-impact 層**(broker 損失函數是 AUM-weighted)、**broker action**(凍結跟單)、**observability = 生死題**(需 order-level 資料，CEX 只給 closed-trade)、reframe 成「Suitability Monitor」、**真實歷史 blow-up 回溯 > synthetic**。

## 🎯 這個 session 最大發現

**Opus 警告的 observability 生死題 → on-chain perp DEX 解掉。**

- **Hyperliquid**：交易全上鏈。官方 API（historicalOrders + vault pnlHistory）+ `hyperliquid-stats` 已有「每 user 清算金額 + leverage + 帳戶價值」= **真實爆倉 master 完整逐筆 + 清算事件 = 現成 ground truth**
- **GMX/Perpy Finance**：鏈上 copy trading vault，個別 leader + 真實 follower 都上鏈 → 能量真實 follower-impact
- **結論**：不用等 OTSO 就能做出「會 close 的真實回溯 demo」。OTSO 從「依賴」變「加分驗證」。

## 2 個交付（這個 session 完成）

1. `README.crypto-drift-draft.md` — repositioning 文案草稿。**不要 push 上線**直到 demo 存在（避免 over-promise）。先用這個 framing 對 Edison 講。
2. `OTSO-DATA-REQUIREMENTS-draft.md` — 給 Edison 的資料需求（升級了 5/18 的 ask，加了 stop_loss_level + account_equity + leverage + copier_count 等 order-level 欄位）。⏰ 趁 Edison 還沒定稿 data agreement 寄出。

## ⏭️ 下一步（筆電接手從這裡開始）

**建議 3 → 1：**

3. **先研究 Hyperliquid API 細節**：確認哪些 endpoint 拿得到真實 trader 逐筆交易 + 清算事件 + leverage + 帳戶價值。**特別確認 stop-loss / trigger orders 公不公開**（停損掛單率是關鍵訊號；拿不到就用 leverage 升高 + 清算前加碼 + 帳戶價值曲線替代）。
   - 起點：Hyperliquid Info endpoint + `historicalOrders` + thunderhead-labs/hyperliquid-stats（GitHub）+ Nansen Perp PnL Leaderboard
1. **Build Hyperliquid 真實回溯 demo**：抓 3-5 個真實爆倉 trader + 2-3 穩定，跑偵測器，證明「清算前 N 筆就標紅 + 穩定的不誤報 + 市場波動的不誤報」。
2. **寄 data schema doc 給 Edison**（鎖 OTSO order-level，為「你平台資料也行」鋪路）。

## Build 時的硬約束（codex + Opus 共識）

- 開 branch `copytrading-drift-demo`（已開，你在這個 branch）。**不碰核心 MCP tools**（`src/tradememory/mcp_server.py`）。
- **賣 lead-time + 可審計 + 鑑別力**，不賣降 DD（MaxDDStop 在 DD 上贏 CUSUM 93.5%）。
- **排除** BOCPD（你研究判 DEAD）、DQS（DEAD）、anti_resonance（decision-time gate 不是 master 監控）、CalibratedAgent（Phase 5 INVALID）、binary CUSUM 當主偵測器。
- **連續訊號**用 `changepoint.py` 的 NIG 或 SSRT `mSPRT_t03`（你自己驗證 Type I<0.05 的唯一方法），不要 binary CUSUM。
- **3 個正交風險軸**（exposure / discipline / tilt），不是 8 個獨立 factor。多重比較校正。`insufficient_data` 狀態。
- **volatility-normalized risk units**（size/equity 或 size/ATR），否則分不出「加大注」vs「市場波動」。
- demo 終點 = broker action（凍結跟單）+ follower-impact（$X AUM / N copier 受影響），不是「我偵測到了」。
- synthetic 只當機制附錄，**真實回溯（Hyperliquid）是主秀**。
- 跑 pytest 確認沒弄壞現有 1374 tests 才 commit。

## Pending（需要你本人）

- 寄 `OTSO-DATA-REQUIREMENTS-draft.md` 給 Edison（或併進他要寄的 data agreement）
- Edison 5/27 說要寄 data agreement，你 5/28 給了 email johnson90207@gmail.com，等他寄
