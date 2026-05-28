# OTSO × TradeMemory — Data Requirements (v0.1 draft)

> 給 Edison 的資料需求清單。目的：跑 Copy-Trading Suitability Monitor 的真實回溯，證明「在 master 拖垮 follower 之前就標紅」。
> ⚠️ 這份升級了 Sean 5/18 的 ask（原本只要 entry/exit/size/timestamp = closed-trade summary，不夠）。

## 為什麼 closed-trade summary 不夠（先講這個）

我們的差異化不是「看 equity curve 知道他在虧」（這個 leaderboard 自己會顯示）。是**在 equity curve 還沒崩之前，從行為訊號抓到 master 變樣**：

- 停損掛單率掉了（91% → 22%）
- 虧損後加碼（revenge sizing）
- 倉位相對權益放大（risk escalation）
- 持倉時間 / 頻率異常

**這些訊號全部需要 order-level 資料。** 如果只給 entry/exit/pnl，我們能算的東西跟 leaderboard 沒兩樣，「early warning」這個賣點就不存在。所以下面 MUST HAVE 的欄位是產品成立的底線。

---

## MUST HAVE — 每筆交易一列（per-trade record）

| 欄位 | 解鎖什麼訊號 |
|---|---|
| `master_id`（hashed 即可）| 分組到每個 master |
| `trade_id` | 去重 |
| `symbol` / instrument | volatility normalization + 策略切換偵測 |
| `direction`（long/short）| 方向偏移 |
| `intended_size` + `filled_size`（或 notional）| sizing escalation（intended≠filled 有意義）|
| `leverage`（或 margin used）| risk escalation |
| `entry_timestamp`（UTC, ms）| 交易頻率、持倉時間 |
| `entry_price` | — |
| `exit_timestamp`（UTC, ms）| 持倉時間 |
| `exit_price` | — |
| `realized_pnl` | outcome |
| ⭐ `stop_loss_level`（進場時設的，有改單的話含修改記錄）| **停損掛單率 / 撤停損 —— 最關鍵的 early 訊號** |
| `take_profit_level`（若有）| discipline |
| ⭐ `account_equity` 或 balance（進場當下）| **把倉位正規化成 risk-unit（size/equity），否則分不出「加大注」vs「帳戶變大」** |

> 沒有 `stop_loss_level` 跟 `account_equity` 這兩個，產品退化成 leaderboard。其他欄位 OTSO 的 raw trade log 應該都有。

## NICE TO HAVE — 有更好

| 欄位 | 解鎖什麼 |
|---|---|
| 改單記錄（SL/TP 中途修改）| discipline drift 更細 |
| `copier_count` per master 隨時間 | **follower-impact：受影響幾個人** |
| `copied_notional` / 跟單 AUM per master 隨時間 | **follower-impact：估計影響 $X** |
| intra-trade MAE/MFE 或 price path | adverse excursion（難拿，可略）|

## 範圍（重要 — 為了真實回溯的 ground truth）

- **5-10 個 master 帳號**
- **≥ 6 個月**歷史
- ⭐ **刻意挑：2-3 個已經爆掉 / 被下架的 master + 2-3 個穩定的**
  → 這樣我能證明「我在爆掉前 N 筆就標紅，穩定的不誤報」。這是整個 demo 說服力的來源（不是 synthetic 自己注入自己抓）

## 匿名化（你方便處理）

- `master_id` / `account_id` hash 掉即可，不需要真名、不需要 PII
- 我這邊不碰錢、不接 API、不下單，只讀 trade log 算分

## 格式

CSV 或 JSONL，一筆交易一列。範例 schema：

```json
{
  "master_id": "hashed_a1b2",
  "trade_id": "T-1001",
  "symbol": "BTCUSDT",
  "direction": "long",
  "intended_size": 0.5,
  "filled_size": 0.5,
  "leverage": 10,
  "entry_ts": "2026-01-03T08:14:22.000Z",
  "entry_price": 42150.0,
  "exit_ts": "2026-01-03T11:02:10.000Z",
  "exit_price": 42890.0,
  "realized_pnl": 370.0,
  "stop_loss": 41800.0,
  "take_profit": 43500.0,
  "account_equity": 25000.0
}
```

## 我交回什麼（一週內）

- 每個 master 的 behavioral risk dossier（drift 紅黃綠燈 + 3 個可審計原因）
- **Lead-time 證明**：爆掉的 master 我在第幾筆就標紅（vs equity drawdown stop 何時觸發）
- 一頁 broker report sample（含 SHA-256 audit hash）
- 穩定 master + 純市場波動 master 不誤報的鑑別力證明

## NDA / 資料協議

走你們法務的版本（你 5/19 說的）。我這邊只需要上面欄位，匿名化後對你們風險最低。
