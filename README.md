# CryptoPlan — 多交易所自動交易機器人

> 一支可同時連接多家加密貨幣期貨交易所、以單進程 `asyncio` 並行運行的全自動交易機器人。
> 自架（self-hosted）、預設紙上模擬（paper-first）、以測試驅動開發（TDD）打造。

本專案的重點在於**交易系統的軟體工程**：交易所抽象層、adapter 模式、正規化資料模型、
故障隔離與故障安全（fail-safe）設計，以及一套涵蓋單元／整合／合約層級的測試網。

---

## 🔒 關於交易策略

> **策略邏輯為專有內容，未包含在本公開版本中。**

進場型態判定、Fibonacci 價位比例、風控倉位公式與分批出場規則等**策略核心**，
已從公開的原始碼、技術文件與規格中移除（`strategy/` 模組僅保留說明佔位）。
你在文件中看到標註 **🔒 策略內容（專有，未公開）** 的空白區塊，即為刻意隱去的部分。

**架構、交易所對接、風控框架、測試與部署皆完整公開**——這也是本專案想展示的工程重點。

---

## ✨ 技術亮點

- **多交易所架構（方案 B：抽象介面 ＋ 混合 adapter）**
  定義統一的 `Exchange` 介面，底下並存兩種實作策略：手刻的 Bitunix REST/WebSocket
  客戶端，以及以 `ccxt` / `ccxt.pro` 覆蓋 BingX／Binance／Bybit／OKX 的通用 adapter。
  策略層與執行器只依賴抽象介面，完全不感知交易所差異。
- **單進程並行、故障隔離**
  `Coordinator` 以 `asyncio.gather` 同時運行多個 `ExchangeSession`；各家**獨立**計算
  倉位與本金告警，任何一家串流斷線或下單失敗都被隔離、發信告警，**不拖垮其他交易所**。
- **正規化資料模型**
  各交易所回應（下單結果、私有 WS 訂單推送、持倉）在 adapter 邊界統一映射為
  `OrderResult` / `OrderEvent` / `Position`，並保留 `raw` 原始欄位以利除錯。
  上層邏輯永遠拿到乾淨、統一的資料。
- **故障安全（fail-safe）預設**
  `testnet` 預設為 `true`——設定缺漏時**退回紙上模擬**而非誤觸真實下單。
  另附價格感知的紙上成交模擬器，可在不動真錢的情況下端到端驗證整套流程。
- **對真實交易所逆向工程並校正**
  Bitunix 官方文件多處與實際不符（WebSocket 網域、REST query 簽名串接規則、
  帳戶端點路徑、私有 WS 訂單狀態欄位名），皆已實連驗證、修正並寫入測試作為回歸網。
- **測試驅動開發**
  **101 個測試案例、23 個測試模組**，涵蓋單元、整合與**跨 adapter 合約測試**——
  任何交易所 adapter 都必須通過同一套介面合約。

---

## 🏗 系統架構

```
                   ┌─────────────────────────────┐
                   │        Coordinator          │
                   │  - 載入 config，建立啟用的    │
                   │    ExchangeSession（1~N 家）  │
                   │  - 全域每日訊號檢查排程        │
                   │  - asyncio.gather 並行跑各家  │
                   └──────────────┬──────────────┘
                                  │ 持有多個
              ┌───────────────────┼───────────────────┐
              ▼                                        ▼
   ┌────────────────────┐                  ┌────────────────────┐
   │ ExchangeSession    │                  │ ExchangeSession    │
   │  (bitunix)         │                  │  (bingx)           │
   │ - 自己的 capital   │                  │ - 自己的 capital   │
   │ - 自己的狀態機/緩衝 │                  │ - 自己的狀態機/緩衝 │
   │ - 自己的 executor  │                  │ - 自己的 executor  │
   │ - 自己的 ws 串流    │                  │ - 自己的 ws 串流    │
   └─────────┬──────────┘                  └─────────┬──────────┘
             │ 只依賴抽象介面                          │
             ▼                                        ▼
   ┌────────────────────┐                  ┌────────────────────┐
   │ BitunixAdapter     │                  │ CcxtAdapter        │
   │ (手刻 rest.py /    │                  │ (ccxt / ccxt.pro， │
   │  ws.py)            │                  │  bingx/binance/…)  │
   └────────────────────┘                  └────────────────────┘
        都實作 ───────►  Exchange 抽象介面  ◄───────
```

**資料流：** 交易所 WebSocket 推送行情 → adapter 統一輸出「已收盤」K 棒事件 →
每個（幣種 × 週期）狀態機消費 → 🔒 策略判定（專有）→ `Executor` 經抽象介面下單 →
私有 WS 訂單推送（正規化為 `OrderEvent`）驅動分批出場與止損管理 → Email 通知關鍵事件。

### 關鍵設計決策

| 決策 | 理由 |
|------|------|
| **抽象介面 ＋ 混合 adapter**（而非全走 ccxt 或全手刻） | 保留已實連驗證的 Bitunix 手刻成果（零浪費），同時用 ccxt 低成本覆蓋一線大所 |
| **語意化下單介面**（`place_entry`/`place_tp`/`place_sl`） | 交易所特定欄位（`tradeSide`、`effect`…）被推進各 adapter 內部，執行器保持輕薄 |
| **`stream_candles` 只吐已收盤 K 棒** | 收盤偵測藏進 adapter，策略層永遠拿到乾淨事件，不必懂各家推送格式差異 |
| **每個 Session 資金／狀態獨立** | 各交易所獨立算倉位與告警；一家異常不影響另一家 |
| **保留 `raw` 原始回應** | 「文件不可信、須核對真實回應」的血淚教訓；除錯必要 |

---

## 🧪 測試

```bash
cd rapid_frame_bot
pip install -r requirements-dev.txt
python -m pytest -v
```

- **單元測試**：資料模型、設定載入、金鑰載入、風控倉位、REST 簽名、Email 組裝、
  紙上模擬器、adapter registry。
- **整合測試**：Bitunix／ccxt adapter、執行器下單路由、多 session 並行、
  開機恢復、實盤就緒檢查、REST 簽名、私有 WS 解析。
- **合約測試**：一組「Exchange 介面合約」，對任何 adapter 都須通過，確保新交易所
  接入時行為一致。

> 🔒 策略本身的單元測試（型態偵測、價位計算）屬專有內容，未包含在本公開版本。

---

## 🛠 技術棧

Python 3.11+ · `asyncio` · `aiohttp` · `websockets` · `ccxt` / `ccxt.pro` ·
`PyYAML` · `loguru` · `pytest` / `pytest-asyncio` · Docker / Docker Compose · SMTP

---

## 📁 專案結構

```
rapid_frame_bot/
├── main.py               # Coordinator：載入設定、並行運行多個 session
├── session.py            # ExchangeSession：單一交易所的獨立執行環境
├── config.py             # 全域 Config + 每家 ExchangeConfig
├── config_secrets.py     # 金鑰載入（環境變數優先，檔案回退）
├── models.py             # 正規化資料模型（Candle / OrderResult / OrderEvent / Position …）
├── shared_state.py       # 持倉鎖、每日訊號計數
│
├── exchanges/            # ★ 交易所抽象層（本專案核心）
│   ├── base.py           #   Exchange 抽象介面（ABC）
│   ├── registry.py       #   名稱 → adapter 類別
│   ├── bitunix/          #   手刻 REST + WebSocket adapter
│   └── ccxt_based/        #   ccxt / ccxt.pro 通用 adapter
│
├── strategy/             # 🔒 策略邏輯（專有，未公開 — 見 strategy/README.md）
├── risk/                 # 倉位計算框架
├── trader/               # 執行器（下單／TP／SL／分批出場路由）＋ 紙上成交模擬器
├── notify/               # Email 通知
├── scripts/              # 唯讀實連探測腳本（probe_*）
└── tests/                # unit / integration / contracts
```

---

## 🚀 執行方式

```bash
cd rapid_frame_bot
pip install -r requirements.txt

# 1. 複製設定範本並填寫
cp config.example.yaml config.yaml

# 2. 填入金鑰（環境變數優先，或見 secrets/README.md）
export BITUNIX_API_KEY=...  BITUNIX_API_SECRET=...

# 3. 啟動（testnet: true 為紙上模擬，不真下單）
python main.py
```

Docker：

```bash
docker compose up -d && docker compose logs -f
```

---

## 📌 現況

- ✅ 多交易所架構（方案 B）已完成並合併；Bitunix 手刻 REST/WS 已對真實環境實連驗證。
- ✅ 紙上模擬、開機恢復、本金告警、Email 通知、Docker 部署皆完成且測試通過。
- 🔧 BingX（ccxt.pro）adapter 的止損參數與 K 線收盤判斷尚待實連校正
  （見 `rapid_frame_bot/docs/BingX_ccxt_校正清單.md`），實盤前務必以紙上模式驗證。

---

## ⚠️ 免責聲明

這是個人技術專案。加密貨幣期貨交易涉及高風險，高槓桿可能造成重大虧損。
本專案不構成任何投資建議，請僅在你能承受的資金範圍內、並自負風險使用。
