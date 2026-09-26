# Entropy & Lighter / Robinhood Hood 自動化價差套利機器人

**[English documentation → README.en.md](README.en.md)**
**[完整繁體中文教學 → TUTORIAL.zh-CN.md](TUTORIAL.zh-CN.md)**
**[新手懶人包（從零開始）→ 新手懶人包.md](新手懶人包.md)**

開源雙交易所永續合約套利機器人。其中一條腿永遠是 **Entropy**（Hyperliquid 上的 `io` builder dex）；另一條腿（對沖腿）三選一：

| `--hedge` 參數 | 交易所 | 計價貨幣 | 吃單手續費 | 協議 |
|---|---|---|---|---|
| `lighter` | Lighter 主網 | USDC | 0 bps | zkLighter ws（增量訂單簿，非同步結算） |
| `lighter-rh` | Lighter Robinhood Chain | **USDG** | 0 bps | zkLighter ws |
| `tradexyz` | Hyperliquid trade.xyz dex | USDC | ~1 bps | HL l2Book，IOC 同步結算 |

> **支持作者** —— 透過以下連結註冊，讓我們一起獲得獎勵：
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

- `midline_bps` —— 溢價的常態水平。請實際測量溢價所在的位置後填入，**填錯即虧損**。
- `upper_bps` / `lower_bps` —— 中樞上下兩側的入場帶寬。

兩個方向的門檻都是**扣除雙邊吃單手續費之後的淨門檻**。一次完整來回扣費後**淨賺 ≥ upper + lower bps**，結構上保證。

## 快速開始

```bash
git clone https://github.com/Procyons666/Entropy-Lighter-RobinHood-Automated-Spread-Arbitrage.git
cd Entropy-Lighter-RobinHood-Automated-Spread-Arbitrage
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp config.example.yaml config.yaml
cp .env.example .env
```

**第一步：先採集數據**（不需要任何密鑰，不會下任何訂單）：

```bash
python3 main.py --record-only --symbol SNDK --hedge lighter-rh --cn
```

至少跑幾個小時（建議一整天），數據寫入 `logs/minutes.csv`。

**第二步：分析數據、取得閾值建議：**

```bash
python3 tools/analyze.py
```

把輸出的 `thresholds:` 區塊貼入 `config.yaml`。

**第三步：填入密鑰，開始實盤：**

```bash
pip install -r requirements-live.txt
python3 main.py --symbol SNDK --hedge lighter-rh --cn
```

本機器人**沒有模擬盤**，啟動即為真實下單。請從最小倉位開始。

## 取得 API 密鑰

**Hyperliquid（Entropy 腿）：**
1. 前往 [https://app.hyperliquid.xyz/API](https://app.hyperliquid.xyz/API)
2. 連接主帳號錢包 → 點擊「Generate API Wallet」
3. 複製 Agent Private Key → 填入 `.env` 的 `HL_PRIVATE_KEY`
4. 複製主帳號地址 → 填入 `.env` 的 `HL_ACCOUNT_ADDRESS`

**Lighter（對沖腿）：**
- Robinhood Chain（推薦）：[https://robinhoodchain.lighter.xyz/?referral=PROCYONSS&source=none](https://robinhoodchain.lighter.xyz/?referral=PROCYONSS&source=none)
- 依照 [lighter-python 文件](https://github.com/elliottech/lighter-python) 建立 API Key

## 配置說明

| 鍵 | 說明 | 預設值 |
|---|---|---|
| `thresholds.midline_bps` | 溢價中樞（**必須實測**） | — |
| `thresholds.upper_bps` / `lower_bps` | 入場帶寬（> 0） | — |
| `*.max_position_usd` | 各所持倉上限 | 1000 |
| `sizing.max_order_notional_usd` | 單筆名義上限 | 500 |
| `execution.premium_persist_sec` | 信號需持續多久才觸發 | 0.3 |

完整參數說明請見：[config.example.yaml](config.example.yaml)

## 目錄結構

```
main.py                       入口
entropy_arb/config.py         配置載入與校驗
entropy_arb/engine.py         策略主循環
entropy_arb/book.py           訂單簿與套利計算
entropy_arb/feeds.py          WebSocket 行情
entropy_arb/venue_hl.py       Hyperliquid 適配器
entropy_arb/venue_lighter.py  Lighter 適配器
entropy_arb/recorder.py       分鐘數據採集
entropy_arb/dashboard.py      Rich 終端儀表板
tools/analyze.py              數據分析 → 閾值建議
```

## 已知風險

- **midline 填錯就是虧損策略** —— 請定期重新採集數據更新
- **USDG 基差**（`lighter-rh`）—— USDG 本身的波動是真實盈虧
- **資金費率** —— 兩所各自獨立，持倉成本未建模，請控制倉位規模
- **薄盤口** —— Entropy 深度可能很小，注意滑點
- **單腿風險** —— 一腿成交後另一腿可能失敗，機器人會自動對沖但需人工監控

風險自負。本軟體直接操作真實資金，不構成任何投資建議。

## 開源授權

[MIT](LICENSE)
