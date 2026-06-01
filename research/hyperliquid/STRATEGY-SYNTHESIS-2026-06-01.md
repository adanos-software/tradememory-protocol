# TradeMemory / Mnemox 戰略綜合 — 5-agent 集思廣益 (2026-06-01)

> 觸發：full-universe run 證偽了 drift 論證後，Sean 退一步問根本問題：論文做來幹嘛？繞一圈後怎麼選？這些對「產品+賺錢」有意義嗎？什麼才「夠看」？現在風頭是什麼、怎麼打入？
> 方法：5 個平行 subagent（first-principles / 市場風頭(WebSearch) / 產品概念(idea-reality) / 變現 / 魔鬼代言人），各自 web 查證 2026-06 現況。以下是綜合。

## A. 5 個 agent 的共識（殘酷真相）

1. **drift 預警 API 商業上已死（5/5 同意）。** 核心宣稱被 Sean 自己的研究證偽（AUC 0.499、recall 3%）；沒人為「證明偵測器無效」付錢；ZuluGuard 14 年已佔位（黑箱+forex）；broker 真正的痛是執行 slippage 不是行為漂移。不是 niche、不是調參能救——是現象不存在。
2. **智識意義 ≠ 商業意義（最危險的自我欺騙）。** 論文（負面結果）智識上真有價值、值得發 arXiv、建立 quant 信用；商業上 = 0。把兩者混為一談會讓你再燒 6 個月。TradeMemory 目前只有 (a) 沒有 (b)。
3. **OSS 1026★ / 813 下載 = vanity，非 demand。** Dev 裝來玩 ≠ broker 付錢。Edison/OTSO 是「禮貌」非「客戶」——walk-away 過又回來、只答應寄 data agreement，無 signed LOI / 報價 / 付費 pilot。
4. **真正的殘值不是 detector（已死），是：** (a) **Hyperliquid on-chain pipeline**（withdrawal-filtered 真實爆倉/行為標註 = 別人沒有的乾淨 ground truth）；(b) **「敢嚴謹證偽自己論文」的研究信用**；(c) **audit/transparency infra**。誤把副產品當包裝、把死掉的 thesis 當主菜。

## B. 當前風頭（2026-06，WebSearch 查證）

- **Agentic trading 剛主流化**：Robinhood Agentic Trading（2026-05-27 上線，2700 萬 funded 戶可經 **MCP** 用 Claude/GPT/Cursor 下單，保留 limits/approval/monitoring）；Public 首家做 AI agent 投組；Kraken(134cmd+MCP)/Binance(7 skills)/OKX(60+ chain)/Coinbase 全 ship agent toolkit。**FINRA 2026 把 AI agent 列新風險類別**，點名 explainability/auditability/可追溯。散戶實測「23 套 AI 系統虧 $12,400」。
- **Hyperliquid = crypto meta**：占 perp DEX 量 44%、日量破 $70 億、HIP-3 builder perps >35% 量、**Vaults 可委派 authorized agent (CoreWriter)**、copy-trading 抽 builder fee（PVP.trade lifetime $7.2M）。
- **Agent memory = 已驗證/募資賽道但全 horizontal**：Mem0 51k★/$24M、Qdrant $50M、Letta/Zep——**沒人做 trading 專用**（TradeMemory 的 vertical niche）。
- **Agent guardrails / 可驗證戰績熱**：Braintrust $80M、Langfuse 被收、Agentic Risk Standard(ARS)；「Q1 2026 無可驗證鏈上指標的 AI 項目全 terminal」；Recall AgentRank 用質押跑 AI trading arena 排行榜。
- **現成收單/分發方**：交易所 agent toolkit（Kraken/Binance/OKX/Coinbase）、Hyperliquid builders/vaults、copy-trade 平台、量化 fund（FINRA 合規壓力最高）。

## C. 綜合推薦（一個產品）

**「可驗證的鏈上交易 / agent 戰績與風險情報」——self-serve 產品**，建在 Hyperliquid pipeline 上，卡在兩個最熱浪潮交叉點：**agentic trading 主流化（Robinhood/MCP + FINRA 要可審計）× Hyperliquid meta（agent-vault + copy-trading 經濟）**。

- **做什麼**：self-serve API + dashboard，對任一交易者/agent 的鏈上紀錄輸出：skill-vs-luck 評分、行為風險、爆倉型態分類、**audit-trail 防偽驗證**（這 leader/agent 戰績是真的嗎、為何爆、留證據）。
- **免費 OSS/MCP TradeMemory = 獲客漏斗**（已有 813/mo 下載、1026★、MCP-native 正好接 Robinhood/交易所 agent 生態）。
- **最窄楔子（2-4 週 solo 可上，選一低競爭切入）**：
  - **① "CI for trading bots"**：agent 決策 replay 歷史 → 過擬合機率 + drift 評分 PASS/FAIL（idea_signal **30 = 最空 lane**；過擬合燒錢是 quant dev 頭號痛；直接複用 pipeline + 你的過擬合/負面研究）。
  - **② copy-trader / agent 戰績驗證**：貼一個地址 → 真本事 vs 運氣 + 風險紅旗（idea_signal 36；散戶/平台/排行榜買單；騎「可驗證戰績」narrative）。
- **信用是武器**：「敢嚴謹證偽自己論文的 quant」→ 你的評分/驗證才可信（對打 ZuluGuard 黑箱 + 一堆灌水排行榜）。**負面論文從「失敗」變「信任徽章」。**

**賺得到嗎**：Agent 4 估 self-serve $99-499/檔、100-300 付費戶 = **$10-30k MRR、12 個月內可信、不需 enterprise sales team**（適合 solo+Kevin）。**唯一明確「夠看」的路。** broker enterprise audit-chain 天花板 $300-600k ARR 但 solo 12 個月簽不動 → 暫不夠看；B2C(3Commas 等)紅海+CAC → vanity；原始 drift API → 已死。

## D. 紀律警告（Agent 5，最重要）

- **先驗證再建，不要再 over-build。** 最便宜測試：拿乾淨 Hyperliquid 數據 + 一個評分/驗證 demo → 問 Edison「願不願付費買乾淨 ground-truth / 戰績驗證」+ 丟 OSS 受眾，**2-3 週內要一個真實付費訊號（哪怕 $500/mo pilot 口頭承諾）**。沒有就別投。
- **誠實機會成本**：GORent / Buzzer / 諾局有真實付費或近付費用戶；TradeMemory 是唯一「零營收 + thesis 死 + 競品成熟」。同樣 6 週投哪邊 12 個月期望值高？（Sean 的 trading/Mnemox trauma context：不硬推 scaling，先解 partner。）
- Agent 5「若被迫一注」：抽出 audit/transparency 做 vendor-neutral 戰績真實性驗證 API 打 ZuluGuard 黑箱弱點——**但只在 3 週內拿到 broker 付費 pilot 口頭承諾才動，否則全停、資源回 GORent/Buzzer。**

## E. 論文怎麼框（回扣暫停的決定）

論文 = **credibility/marketing 資產，不是產品**。用 **reframe-as-強負面（便宜、誠實、快）** 收尾發 arXiv，當上面那個「可信評分/驗證」產品的信任背書。**別再把論文當產品雕。** → 框架走 **Option A（強負面）**，低成本完成，服務於品牌。

## F. 給 Sean 的決策
1. 「可驗證鏈上交易/agent 情報」（self-serve，騎 Hyperliquid+agentic+FINRA 浪）方向有沒有打到你？
2. 還是聽完覺得 TradeMemory 整條該收、資源回 GORent/Buzzer（Agent 5 的 8/10 abandon 案）？
3. 若做 → 先 2-3 週 demand 驗證（Claude 可幫做 demo + 擬 Edison 提問），不直接 build？
4. 論文 → 確認走 Option A 強負面、低成本收尾發 arXiv 當信任徽章？

> 全部 agent 來源見各自輸出（Robinhood/CNBC, Hyperliquid/Dwellir, Mem0, FINRA 2026, ZuluTrade, idea-reality idea_check 等）。
