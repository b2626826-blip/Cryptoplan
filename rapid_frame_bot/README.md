# 急速框交易機器人

Bitunix Futures「做多急速框」自動交易機器人。

## 快速開始

```bash
pip install -r requirements.txt
# 編輯 config.yaml 填入 API Key（testnet: true 為 Paper Trade 模式）
python main.py
```

## 測試

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

## Docker 部署

```bash
docker compose up -d
docker compose logs -f
```

## 模式說明

- `testnet: true` → Paper Trade：所有下單只寫 Log，不實際送出（用於驗證策略邏輯）。
- `testnet: false` → 真實下單。

系統架構與 API 對接見根目錄 `README.md` 與 `急速框交易機器人_技術文件.md`（架構篇）；
操作細節見 `docs/操作手冊.md`。🔒 策略內容為專有，未公開。
