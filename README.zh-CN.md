# Entropy & Lighter / Robinhood Hood 自動化價差套利機器人

**[English documentation / 英文文檔 → README.md](README.md)**
**[完整繁體中文教學 → TUTORIAL.zh-CN.md](TUTORIAL.zh-CN.md)**
**[新手懶人包（從零開始）→ 新手懶人包.md](新手懶人包.md)**

開源雙交易所永續合約套利機器人。其中一條腿永遠是 **Entropy**（Hyperliquid 上的 `io` builder dex）；另一條腿（對沖腿）三選一：

| `--hedge` 參數 | 交易所 | 計價貨幣 | 吃單手續費 | 協議 |
|---|---|---|---|---|
| `lighter` | Lighter 主網 | USDC | 0 bps | zkLighter ws（增量訂單簿，非同步結算） |
| `lighter-rh` | Lighter Robinhood Chain | **USDG** | 0 bps | zkLighter ws |
| `tradexyz` | Hyperliquid trade.xyz dex | USDC | ~1 bps | HL l2Book，IOC 同步結算 |

> **推薦連結** —— 透過以下連結註冊即可支持本專案：
> - Entropy — 享 25% 費率優惠：<https://entropy.io/?r=procyons>
> - Lighter Robinhood Chain：<https://robinhoodchain.lighter.xyz/?referral=PROCYONSS&source=none>

當同一個交易品種在一邊貴、另一邊便宜時，機器人會同時在貴的一邊賣出、便宜的一邊買入（均為吃單），持有 delta 中性倉位，等溢價回歸後反向平倉。所有交易決策使用的價格都來自**將要實際成交的那個交易所的真實訂單簿**——Hyperliquid 的盤口來自官方 WebSocket（`wss://api.hyperliquid.xyz/ws`），Lighter 的盤口來自 Lighter 官方 WebSocket。

機器人運行期間（即使沒有密鑰、沒有開策略）會自動把兩邊盤口記錄成**分鐘級 CSV 數據**，配套的分析工具可以直接把這些數據變成策略所需的三個核心參數。

## 信號邏輯

整個信號就是 `config.yaml` 裡三個數字，由你根據採集的數據自己設定：

```
premium_bps =（Entropy 價格 / 對沖腿價格 − 1）× 10,000

                          ┌──────────────  賣出 Entropy + 買入對沖腿
midline + upper  ───────────────────────────────────────────────────
                                       ▲
midline          ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┼ ─ ─   溢價的長期中樞
                                       ▼
midline − lower  ───────────────────────────────────────────────────
                          └──────────────  買入 Entropy + 賣出對沖腿
```

- `midline_bps` —— 溢價的常態水平。跨所溢價幾乎從不以零為中心（預言機不同、計價貨幣不同、新上市溢價等），零中心的帶只會朝一個方向開倉、打滿倉位上限、永遠無法平倉。請實際測量溢價所在的位置，然後填入。
- `upper_bps` / `lower_bps` —— 中樞上下兩側的入場帶寬。

兩個方向的門檻都作用於**可實際成交的價格**（Entropy 買一 對 對沖腿賣一，反之亦然），並且是**扣除雙邊吃單手續費之後的淨門檻**——引擎會在閾值之上另行疊加手續費。因此一次完整來回扣費後**淨賺 ≥ upper + lower bps**，這是結構上保證的。

有一點必須理解：當 `midline_bps: 5` 時，買入 Entropy 的門檻是 `lower − midline`，可能為**負數**。這是有意為之——如果 Entropy 長期貴 5 bps，那麼在溢價為 0 時買入它，相對其自身均衡水平就是便宜了 5 bps，這筆交易正是此前在 `midline + upper` 處賣出的獲利平倉。這同時意味著**中樞填錯就是虧損策略**：若真實溢價中樞是 0 而你填了 5，機器人會整天以公允價買入 Entropy。先測量、再交易——數據採集器和分析工具就是為此而生。

## 快速開始

```bash
git clone https://github.com/你的帳號/entropy-arb.git && cd entropy-arb
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # 數據採集只需要這些

cp config.example.yaml config.yaml       # 策略配置（閾值、規模、風控）
cp .env.example .env                     # 密鑰——交易必填
```

交易哪個市場**不在**配置文件中——每次啟動時用命令列參數顯式指定：`--symbol`（兩個交易所共同交易的品種）和 `--hedge`（三選一：`lighter`、`lighter-rh`、`tradexyz`；Entropy 永遠是另一條腿）。

本機器人**沒有模擬盤**——要麼採集數據（`--record-only`），要麼實盤交易。請用採集的數據和最小的倉位上限來驗證策略，而不是模擬成交。

**第一步：先採集數據**（不需要任何密鑰）：

```bash
python3 main.py --record-only --symbol SNDK --hedge lighter-rh
```

至少運行幾個小時（最好一整天——溢價存在日內規律），數據寫入 `logs/minutes.csv`。

**第二步：分析數據、設定閾值：**

```bash
python3 tools/analyze.py
```

它會輸出溢價分佈、各檔帶寬的歷史觸發頻率，以及可直接貼入 `config.yaml` 的 `thresholds:` 配置區塊。

**第三步：實盤** —— 填寫 `.env`，安裝簽名 SDK，倉位上限從剛好滿足交易所最小名義的水平開始：

```bash
pip install -r requirements-live.txt
python3 main.py --symbol SNDK --hedge lighter-rh
```

不帶 `--record-only` 運行時，只要兩邊行情就緒且溢價越過帶寬，就會立即發送真實訂單。

**儀表板。** 在終端運行時會顯示實時 Rich 儀表板：兩邊盤口（含數據齡/點差）、倉位與上限、帳戶權益與本次會話盈虧、兩個方向的可成交溢價對比完整門檻（已含手續費與庫存加價，● 表示已武裝）、數據採集進度、最近成交，以及日誌尾部（完整日誌寫入 `logging.file`，預設 `logs/engine.log`）。`--record-only` 模式同樣可用。加 `--cn` 參數可使儀表板全部以中文顯示。`--no-dashboard` 可切換為純日誌輸出（nohup/systemd 等非終端環境會自動退回純日誌），也可設置 `logging.dashboard: false`。

## 數據採集與分析

採集器在所有模式下自動運行（`recorder.enabled: true`）：每秒採樣一次兩邊的真實盤口，每分鐘寫一行：

| 欄位 | 說明 |
|---|---|
| `minute_ts`, `time_utc` | 分鐘起點（epoch 秒 / ISO UTC） |
| `entropy_bid/ask`, `hedge_bid/ask` | 該分鐘最後一次有效盤口 |
| `premium_open/high/low/close/mean/std_bps` | Entropy 相對對沖腿的中間價溢價 |
| `sell_edge_mean/max_bps` | 賣出 Entropy 方向的可成交溢價（Entropy 買一 / 對沖腿賣一 − 1） |
| `buy_edge_mean/max_bps` | 買入 Entropy 方向的可成交溢價（對沖腿買一 / Entropy 賣一 − 1） |
| `samples` | 該分鐘約 60 秒中兩邊盤口同時有效的秒數 |

採集的 edge 為費前口徑；分析工具在統計觸發頻率前會先扣除 `--fees-bps`（請傳入**兩邊吃單費之和**——零費交易所預設 0.0，對沖腿為 `tradexyz` 時約為 1.0），因此其表格與建議值可直接填入配置。`--hours 24` 可只分析最近數據；溢價中樞會漂移，請定期重新分析並更新 `config.yaml`。

## 配置說明

策略在 `config.yaml`（嚴格校驗——未知鍵名直接報錯），密鑰在 `.env`。交易市場由命令列指定（`--symbol`、`--hedge`）。完整的雙語注釋參考：[config.example.yaml](config.example.yaml)。核心項：

| 鍵 | 說明 | 預設值 |
|---|---|---|
| `thresholds.midline_bps` | 溢價中樞（必須實測！） | — |
| `thresholds.upper_bps` / `lower_bps` | 入場帶寬（> 0） | — |
| `entropy.dex` | Entropy 在 Hyperliquid 上的 dex 名 | `io` |
| `*.taker_fee_bps` | 各所吃單費 | 0.0（tradexyz 對沖腿：1.0） |
| `*.max_position_usd` | 各所持倉上限 | 1000 |
| `*.max_orders_per_min` | 各所每分鐘下單預算（滑動 60 秒） | 120；Lighter 對沖腿 30 |
| `sizing.take_fraction` | 吃掉可套利深度的比例 | 0.5 |
| `sizing.max_order_notional_usd` | 單筆名義上限 | 500 |
| `inventory.scale_bps` / `floor_frac` | 庫存階梯（倉位超過上限的 `floor_frac` 後額外加價） | 10 / 0.5 |
| `execution.premium_persist_sec` | 信號需持續多久才觸發 | 0.3 |
| `execution.*` | 滑點保護、超時、對帳週期等 | 見配置文件 |
| `recorder.*` | 分鐘數據採集器 | 開啟，`logs/minutes.csv` |
| `logging.dashboard` / `logging.file` | 終端儀表板；開啟時日誌寫入文件 | 開啟，`logs/engine.log` |

## 密鑰配置（`.env`，僅實盤需要）

**Entropy / Hyperliquid API Key 取得方式：**

1. 前往 [https://app.hyperliquid.xyz/API](https://app.hyperliquid.xyz/API)
2. 連接你的主帳號錢包
3. 點擊「Generate API Wallet」建立 Agent 代理錢包
4. 複製 **Agent Private Key** → 填入 `HL_PRIVATE_KEY`
5. 複製你的**主帳號地址** → 填入 `HL_ACCOUNT_ADDRESS`

> `HL_PRIVATE_KEY` 填的是 Agent 代理錢包私鑰，不是主帳號私鑰。使用 `--hedge tradexyz` 時兩條腿預設共用該帳戶；如需獨立帳戶，設置 `HL_PRIVATE_KEY_XYZ` / `HL_ACCOUNT_ADDRESS_XYZ`。

**Lighter API Key 取得方式：**

- 主網：[https://mainnet.zklighter.elliot.ai](https://mainnet.zklighter.elliot.ai)
- Robinhood Chain（推薦）：[https://robinhoodchain.lighter.xyz/?referral=PROCYONSS&source=none](https://robinhoodchain.lighter.xyz/?referral=PROCYONSS&source=none)
- 依照 [lighter-python 文件](https://github.com/elliottech/lighter-python) 建立 API Key，填入 `LIGHTER_ACCOUNT_INDEX`、`LIGHTER_API_KEY_INDEX`、`LIGHTER_API_PRIVATE_KEY`

> 注意：Lighter 主網與 Robinhood Chain 是**兩套完全獨立的帳號與密鑰**，必須與 `--hedge` 參數一致。

## 執行機制

- 兩條腿**同時發出吃單**：Lighter 用帶均價保護的市價單，在鑑權 WebSocket 上非同步確認成交；Hyperliquid 用 IOC 限價單同步結算（結果未知時輪詢 orderStatus 兜底）。
- **持續性閘門**（`premium_persist_sec`）：信號先「武裝」，持續存在才觸發，過濾單 tick 的假信號。
- **庫存階梯**：倉位超過上限的 `floor_frac` 後，同方向加倉需要線性遞增的額外溢價，滿倉時最高加 `scale_bps`。
- **淨敞口對沖**：兩腿成交不對等時立即用 reduce-only 單（帶滑點保護）削減敞口，並每 `reconcile_sec` 與鏈上倉位對帳。
- **故障隔離**：被限頻的交易所短暫暫停；交易所不可達（如例行維護）時暫停交易並每 `venue_probe_sec` 探測直至恢復；連續 `max_consecutive_errors` 次執行異常則整體停機。
- **僅實盤**：沒有模擬成交模式。`--record-only` 是唯一無風險的運行方式，其餘都是真金白銀。

## 目錄結構

```
main.py                  入口（--record-only，預設即實盤）
entropy_arb/config.py    YAML + .env 配置契約與校驗
entropy_arb/book.py      訂單簿 + 含手續費的套利規模計算
entropy_arb/feeds.py     官方 HL ws + zkLighter ws 行情
entropy_arb/venue_hl.py  Hyperliquid dex 適配器（Entropy、tradexyz）
entropy_arb/venue_lighter.py  zkLighter 適配器（主網、Robinhood Chain）
entropy_arb/engine.py    雙交易所策略主循環
entropy_arb/dashboard.py Rich 終端儀表板
entropy_arb/recorder.py  分鐘級盤口數據採集
tools/analyze.py         minutes.csv -> 閾值建議
tests/                   python3 -m pytest tests/
```

## 已知風險

- **中樞填錯就是虧損策略。** 溢價中樞會漂移，請定期重新測量並保持 `config.yaml` 與市場同步。
- **USDG 基差**（`lighter-rh`）：對沖腿以 USDG 計價，持續溢價中有一部分是穩定幣本身的基差；midline 吸收其水平，但 USDG 的變動是真實盈虧。
- **資金費率**：兩個交易所、兩套獨立的資金費率，持倉成本未建模——倉位上限請設小一些。
- **薄盤口**：Entropy 深度可能很小；`take_fraction` 與名義上限控制單筆規模，但部分成交後對沖腿的滑點是真實存在的。
- **交易時段**：股票類永續（如 SNDK）盤後各所預言機行為不同，建議加寬帶寬或暫停運行。
- **單腿風險**：一條腿成交後另一條可能失敗。機器人會自動對沖並對帳，但仍需人工關注。

風險自負。本軟體直接操作真實資金，本文件不構成任何投資建議。請從最小的倉位上限開始。

## 開源授權

[MIT](LICENSE)
