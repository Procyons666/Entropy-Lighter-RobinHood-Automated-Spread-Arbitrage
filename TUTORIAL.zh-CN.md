# Entropy & Lighter / Robinhood Hood 自動化價差套利機器人
## 完整使用教學

> **語言**：本文件為繁體中文教學。英文版請參閱 [README.md](README.md)，簡體中文版請參閱 [README.zh-CN.md](README.zh-CN.md)。

---

## 支持作者

如果這個專案對你有幫助，歡迎透過以下邀請連結註冊，讓我們一起獲得獎勵：

- **Lighter Robinhood Chain**：[https://robinhoodchain.lighter.xyz/?referral=PROCYONSS&source=none](https://robinhoodchain.lighter.xyz/?referral=PROCYONSS&source=none)
- **Entropy Finance**（享有 25% 費率優惠）：[https://entropy.io/?r=procyons](https://entropy.io/?r=procyons)

---

## 目錄

1. [專案介紹](#1-專案介紹)
2. [運作原理](#2-運作原理)
3. [前置準備](#3-前置準備)
4. [安裝步驟](#4-安裝步驟)
5. [取得 API 密鑰](#5-取得-api-密鑰)
6. [第一階段：數據採集](#6-第一階段數據採集)
7. [第二階段：分析閾值](#7-第二階段分析閾值)
8. [第三階段：設定策略參數](#8-第三階段設定策略參數)
9. [第四階段：實盤交易](#9-第四階段實盤交易)
10. [儀表板說明](#10-儀表板說明)
11. [風險控管](#11-風險控管)
12. [常見問題](#12-常見問題)
13. [目錄結構](#13-目錄結構)

---

## 1. 專案介紹

本機器人是一個**開源的雙交易所永續合約套利系統**，專為以下交易對設計：

- **固定腿（Entropy）**：Hyperliquid 上的 `io` builder dex（Entropy Finance）
- **對沖腿（Hedge）**：三選一

| `--hedge` 參數 | 交易所 | 計價貨幣 | 吃單手續費 |
|---|---|---|---|
| `lighter` | Lighter 主網 | USDC | 0 bps |
| `lighter-rh` | Lighter Robinhood Chain | USDG | 0 bps |
| `tradexyz` | Hyperliquid trade.xyz | USDC | ~1 bps |

當同一個交易品種在 Entropy 貴、在對沖腿便宜時，機器人會同時在貴的一邊賣出、便宜的一邊買入，持有 delta 中性倉位，等溢價回歸後反向平倉獲利。

**沒有模擬盤**。使用 `--record-only` 採集數據，其餘情況均為真實下單。

---

## 2. 運作原理

### 溢價計算公式

```
premium_bps = (Entropy 價格 / 對沖腿價格 - 1) × 10,000
```

### 信號邏輯

```
溢價超過 midline + upper_bps   →   賣出 Entropy + 買入對沖腿
溢價低於 midline - lower_bps   →   買入 Entropy + 賣出對沖腿
```

```
midline + upper  ─────────────────────── (觸發：賣出 Entropy)
                          ↑
midline          ─ ─ ─ ─ ─ ┼ ─ ─   溢價長期中樞
                          ↓
midline - lower  ─────────────────────── (觸發：買入 Entropy)
```

### 核心邏輯

- **midline_bps**：溢價的長期中樞，**必須從實際採集的數據中計算**，不可猜測
- **upper_bps / lower_bps**：中樞上下的入場帶寬（扣除手續費後的淨值）
- 一次完整來回，扣費後淨賺 **≥ upper + lower bps**（結構性保證）

> **重要**：midline 填錯就是虧損策略。請務必先採集數據再設定。

---

## 3. 前置準備

### 系統需求

- Python 3.10 或更新版本
- macOS / Linux / Windows（Linux 伺服器推薦）
- 穩定的網路連線（最好接近交易所機房）

### 需要準備的帳號

| 帳號 | 用途 | 是否必需 |
|---|---|---|
| Hyperliquid 帳號 | Entropy 腿交易 | 是 |
| Lighter 帳號 | 對沖腿（若選 lighter/lighter-rh） | 視 --hedge 參數 |

---

## 4. 安裝步驟

### 步驟一：下載程式碼

```bash
git clone https://github.com/你的帳號/entropy-arb.git
cd entropy-arb
```

### 步驟二：建立 Python 虛擬環境

```bash
python3 -m venv .venv
source .venv/bin/activate   # macOS / Linux
# 若是 Windows：.venv\Scripts\activate
```

### 步驟三：安裝基礎套件（數據採集用）

```bash
pip install -r requirements.txt
```

### 步驟四：複製設定檔模板

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

### 步驟五：安裝實盤套件（實盤交易才需要）

```bash
pip install -r requirements-live.txt
```

---

## 5. 取得 API 密鑰

### Hyperliquid API Key（Entropy 腿必填）

> 建議先透過邀請連結註冊 Entropy，享有 **25% 費率優惠**：
> [https://entropy.io/?r=procyons](https://entropy.io/?r=procyons)

**取得步驟：**

1. 前往 [https://app.hyperliquid.xyz/API](https://app.hyperliquid.xyz/API)
2. 用 MetaMask 或其他錢包連接你的**主帳號**（這是你資金所在的帳號）
3. 在頁面上點擊 **「Generate API Wallet」** 或 **「Create Agent」**
4. 系統會自動產生一個新的 **Agent（代理）錢包**，專門用於 API 簽名
5. 頁面會顯示：
   - **Agent Private Key**（以 `0x` 開頭的 64 位 hex 字串）→ 複製並填入 `.env` 的 `HL_PRIVATE_KEY`
   - **你的主帳號地址**（以 `0x` 開頭，可在錢包查看）→ 填入 `.env` 的 `HL_ACCOUNT_ADDRESS`
6. 前往 Entropy Finance，確認已在 `io` dex 充入足夠的 USDC 保證金

**重要說明：**
- `HL_PRIVATE_KEY` 填的是 **Agent 代理錢包私鑰**，不是你主帳號的私鑰
- Agent 錢包只有交易授權，無法提款，洩露風險遠低於主帳號私鑰
- 如果懷疑 Agent Key 洩露，可隨時在同一頁面撤銷並重新生成，不影響資金

### Lighter API Key（對沖腿，若選 lighter 或 lighter-rh）

> 建議透過邀請連結註冊 Lighter Robinhood Chain：
> [https://robinhoodchain.lighter.xyz/?referral=PROCYONSS&source=none](https://robinhoodchain.lighter.xyz/?referral=PROCYONSS&source=none)

1. 前往對應平台完成帳號註冊：
   - Lighter 主網：[https://mainnet.zklighter.elliot.ai](https://mainnet.zklighter.elliot.ai)
   - Robinhood Chain：使用上方邀請連結
2. 依照 [lighter-python 官方文件](https://github.com/elliottech/lighter-python) 的說明建立 API Key
3. 建立後取得以下三個值，填入 `.env`：
   - `LIGHTER_ACCOUNT_INDEX`（你的帳號序號）
   - `LIGHTER_API_KEY_INDEX`（API Key 序號）
   - `LIGHTER_API_PRIVATE_KEY`（API 私鑰）

> **重要**：Lighter 主網與 Robinhood Chain 是**兩套完全獨立的帳號與密鑰**，必須與啟動參數 `--hedge lighter` 或 `--hedge lighter-rh` 對應，不可混用。

### 填寫 .env 檔案

```env
# Hyperliquid（Entropy 腿）
HL_PRIVATE_KEY=0x你的Agent錢包私鑰
HL_ACCOUNT_ADDRESS=0x你的主帳號地址

# Lighter（對沖腿）
LIGHTER_ACCOUNT_INDEX=你的帳號索引
LIGHTER_API_KEY_INDEX=你的API Key索引
LIGHTER_API_PRIVATE_KEY=你的API私鑰
```

> **安全提醒**：`.env` 檔案已被 `.gitignore` 排除，絕對不會被上傳到 GitHub。請勿手動強制加入 git。

---

## 6. 第一階段：數據採集

**目的**：在不下任何訂單的情況下，觀察兩個交易所之間的溢價分佈，作為設定策略參數的依據。

**這個階段不需要 API 密鑰。**

### 啟動採集

```bash
# 採集 SNDK 的 Entropy vs Lighter Robinhood Chain 溢價數據
python3 main.py --record-only --symbol SNDK --hedge lighter-rh

# 採集 ANTHROPIC（Entropy 上代號 ANTH）的數據
python3 main.py --record-only --symbol ANTHROPIC --entropy-symbol ANTH --hedge lighter-rh --cn
```

參數說明：
- `--record-only`：僅採集數據，不執行任何交易
- `--symbol`：交易品種名稱（對沖腿使用的代號）
- `--entropy-symbol`：若 Entropy 上的代號不同，用此覆蓋
- `--hedge`：對沖腿選擇（`lighter`、`lighter-rh`、`tradexyz`）
- `--cn`：儀表板顯示中文

### 採集時間建議

| 最短時間 | 建議時間 | 說明 |
|---|---|---|
| 2 小時 | 24 小時以上 | 溢價有日內規律，數據越多越準確 |

數據存放位置：`logs/minutes.csv`

### 採集的數據欄位說明

| 欄位 | 說明 |
|---|---|
| `minute_ts` / `time_utc` | 分鐘時間戳 |
| `entropy_bid/ask` | Entropy 盤口 |
| `hedge_bid/ask` | 對沖腿盤口 |
| `premium_mean_bps` | 該分鐘平均溢價（中間價基準） |
| `sell_edge_mean/max_bps` | 賣出 Entropy 方向的可成交溢價 |
| `buy_edge_mean/max_bps` | 買入 Entropy 方向的可成交溢價 |
| `samples` | 該分鐘兩邊盤口同時有效的秒數 |

---

## 7. 第二階段：分析閾值

採集足夠數據後，執行分析工具：

```bash
python3 tools/analyze.py
```

### 進階選項

```bash
# 只分析最近 24 小時的數據
python3 tools/analyze.py --hours 24

# 若使用 tradexyz 對沖腿（有約 1 bps 手續費）
python3 tools/analyze.py --fees-bps 1.0
```

### 輸出範例說明

分析工具會輸出：
1. **溢價分佈圖**：顯示溢價的歷史範圍
2. **觸發頻率表**：各檔帶寬的歷史觸發次數
3. **建議設定**：可直接貼入 `config.yaml` 的 `thresholds:` 區塊

輸出範例：
```yaml
thresholds:
  midline_bps: 55.0    # 溢價長期中樞
  upper_bps: 15.0      # 賣出 Entropy 的門檻（中樞 + 15 bps）
  lower_bps: 15.0      # 買入 Entropy 的門檻（中樞 - 15 bps）
```

> **重要**：midline 是整個策略的核心。填錯了就是持續虧損。溢價中樞會隨時間漂移，**建議每週重新分析一次**。

---

## 8. 第三階段：設定策略參數

編輯 `config.yaml`，主要需要調整的參數：

### 核心信號參數（來自分析工具）

```yaml
thresholds:
  midline_bps: 55.0   # 從 tools/analyze.py 取得
  upper_bps: 15.0     # 從 tools/analyze.py 取得
  lower_bps: 15.0     # 從 tools/analyze.py 取得
```

### 倉位控管

```yaml
entropy:
  max_position_usd: 3000    # Entropy 腿最大名義倉位（USD）

hedge:
  max_position_usd: 3000    # 對沖腿最大名義倉位（USD）

sizing:
  max_order_notional_usd: 1000  # 單次最大下單名義金額
  min_order_notional_usd: 10    # 低於此金額不下單（避免粉塵單）
  take_fraction: 0.5            # 吃掉可套利深度的比例
```

> **新手建議**：先將 `max_position_usd` 設為 100-500 USD 測試，確認運作正常後再調大。

### 執行參數（通常不需修改）

```yaml
execution:
  leg_slippage_bps: 50.0      # 每腿的滑點保護
  settle_timeout_sec: 10.0    # 等待成交確認的超時時間
  max_consecutive_errors: 3   # 連續錯誤幾次後停機
```

---

## 9. 第四階段：實盤交易

### 確認清單

在實盤前，請確認：

- [ ] `.env` 已填入正確的 API 密鑰
- [ ] `config.yaml` 的 midline 已從實際數據計算
- [ ] 兩邊交易所帳戶有足夠保證金
- [ ] 倉位上限設定為可接受的小額（新手建議 ≤ $500）
- [ ] `requirements-live.txt` 套件已安裝

### 啟動實盤

```bash
# 基本啟動
python3 main.py --symbol SNDK --hedge lighter-rh

# Entropy 代號與對沖腿不同時（例如 ANTHROPIC / ANTH）
python3 main.py --symbol ANTHROPIC --entropy-symbol ANTH --hedge lighter-rh --cn

# 後台執行（使用 nohup）
nohup python3 main.py --symbol SNDK --hedge lighter-rh --no-dashboard > logs/nohup.log 2>&1 &
```

### 使用 run.sh 快速啟動

修改 `run.sh` 為你的交易品種，然後直接執行：

```bash
chmod +x run.sh
./run.sh
```

### 停止機器人

在終端按 `Ctrl+C`，或對後台進程發送 `SIGTERM`：

```bash
kill $(pgrep -f "main.py")
```

機器人會完成當前操作後安全退出。

---

## 10. 儀表板說明

在終端執行時，機器人會顯示實時 Rich 儀表板：

```
┌─ 盤口 ──────────────────────────────────────────┐
│ ENTROPY   2156.50 / 2156.70   (age: 0.2s)       │
│ RH        2171.20 / 2171.40   (age: 0.1s)        │
├─ 信號 ──────────────────────────────────────────┤
│ 賣出方向   +68.6 bps  門檻 +70.0 bps   (未觸發) │
│ 買入方向   -62.4 bps  門檻 -40.0 bps   (未觸發) │
├─ 倉位 ──────────────────────────────────────────┤
│ ENTROPY   +0.000  上限 $3000                     │
│ RH        +0.000  上限 $3000                     │
├─ 損益 ──────────────────────────────────────────┤
│ 本次會話  $+12.45                               │
└─────────────────────────────────────────────────┘
```

| 指示 | 說明 |
|---|---|
| `●` | 信號已武裝，等待觸發 |
| `age: Xs` | 盤口數據距上次更新的秒數（越小越新鮮） |

### 儀表板控制

```bash
--cn            # 中文顯示
--no-dashboard  # 純日誌模式（適合 nohup / systemd）
--dashboard     # 強制啟用儀表板（即使非 tty 環境）
```

---

## 11. 風險控管

### 必須了解的風險

| 風險 | 說明 | 應對方式 |
|---|---|---|
| **midline 漂移** | 溢價中樞隨時間改變 | 定期重新分析，每週更新 config.yaml |
| **USDG 基差** | lighter-rh 以 USDG 計價，有穩定幣脫鉤風險 | 監控 USDG 匯率 |
| **資金費率** | 兩個交易所各自獨立的資金費 | 控制倉位規模 |
| **薄盤口** | Entropy 深度可能很小，滑點較大 | 調低 take_fraction 和 max_order_notional_usd |
| **單腿風險** | 一腿成交後另一腿可能失敗 | 機器人自動對沖，但需人工監控 |
| **股票類永續盤後** | 非交易時間預言機行為各所不同 | 考慮加寬帶寬或暫停運行 |

### 建議的啟動流程

```
1. --record-only 採集 24 小時數據
2. 用 tools/analyze.py 確認溢價分佈合理
3. 設定極小倉位（$100 以下）實盤測試 2-4 小時
4. 確認執行正常後再逐步調大倉位
5. 定期重新採集數據並更新 midline
```

> 本軟體直接操作真實資金。任何設定錯誤都可能造成損失。請從最小倉位開始，充分理解運作機制後再擴大規模。

---

## 12. 常見問題

### Q：啟動時出現 `config error: config file 'config.yaml' not found`

```bash
cp config.example.yaml config.yaml
```

### Q：啟動時出現 `startup error: HL credentials missing`

請確認 `.env` 中的 `HL_PRIVATE_KEY` 和 `HL_ACCOUNT_ADDRESS` 已正確填寫。

### Q：看到 `WARNING: RECORD-ONLY`

這是正常訊息，表示你正在使用 `--record-only` 模式，不會下任何訂單。

### Q：信號一直顯示「未觸發」

可能原因：
1. midline_bps 設定不準確 → 重新採集數據並分析
2. 帶寬設定過大 → 可適當縮小 upper_bps 和 lower_bps
3. 市場目前溢價穩定 → 正常現象，等待機會

### Q：如何確認訂單有成交？

查看 `logs/trades.csv`，每筆成交都會記錄在此。

### Q：如何在伺服器上持續運行？

使用 `systemd` 或 `screen`：

```bash
# 使用 screen
screen -S entropy-arb
./run.sh
# Ctrl+A 然後 D 來 detach

# 使用 nohup
nohup python3 main.py --symbol SNDK --hedge lighter-rh --no-dashboard \
  > logs/nohup.log 2>&1 &
```

### Q：`logs/` 資料夾的檔案多大？

- `logs/minutes.csv`：每分鐘一行，每天約 1,440 行，幾十 KB
- `logs/trades.csv`：每筆交易一行，視頻率而定
- `logs/engine.log`：詳細運行日誌，長時間運行可能較大

---

## 13. 目錄結構

```
entropy-arb/
├── main.py                    # 程式入口
├── config.yaml                # 策略設定（本地，不上傳）
├── config.example.yaml        # 策略設定模板（可公開）
├── .env                       # API 密鑰（本地，不上傳）
├── .env.example               # 密鑰模板（可公開）
├── requirements.txt           # 基礎套件（數據採集）
├── requirements-live.txt      # 實盤套件（含 SDK）
├── run.sh                     # 快速啟動腳本
├── record.sh                  # 快速採集腳本
│
├── entropy_arb/               # 核心模組
│   ├── config.py              # 設定載入與驗證
│   ├── engine.py              # 策略主循環
│   ├── book.py                # 訂單簿與套利計算
│   ├── feeds.py               # WebSocket 行情接收
│   ├── venue_hl.py            # Hyperliquid 交易適配器
│   ├── venue_lighter.py       # Lighter 交易適配器
│   ├── recorder.py            # 分鐘數據採集器
│   └── dashboard.py           # Rich 終端儀表板
│
├── tools/
│   ├── analyze.py             # 分鐘數據分析 → 閾值建議
│   ├── backtest.py            # 回測工具
│   └── backtest_v2.py         # 回測工具 v2
│
├── tests/                     # 單元測試
│   ├── test_engine.py
│   ├── test_book.py
│   ├── test_config.py
│   ├── test_recorder.py
│   └── test_dashboard.py
│
└── logs/                      # 運行日誌（本地，不上傳）
    ├── minutes.csv
    ├── trades.csv
    └── engine.log
```

### .gitignore 保護的檔案（不會上傳到 GitHub）

```
.env          ← API 密鑰
config.yaml   ← 含有策略設定（個人化）
logs/         ← 運行日誌與交易記錄
__pycache__/  ← Python 編譯快取
```

---

## 授權

本專案採用 [MIT License](LICENSE) 授權，歡迎自由使用與修改。

---

*本文件不構成任何投資建議。使用本軟體的風險由使用者自行承擔。*
