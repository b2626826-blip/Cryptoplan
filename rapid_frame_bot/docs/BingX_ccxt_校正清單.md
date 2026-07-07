# BingX / ccxt 校正清單（實盤前）

**建立：** 2026-07-02　**對象：** `exchanges/ccxt_based/adapter.py`（`CcxtAdapter`）
**背景：** 多交易所方案 B 已合併；BingX 走 `ccxt.pro`。以下把 adapter 內「計畫預設值」
逐項標出，並記錄哪些已用**無金鑰**方式確認、哪些仍需**唯讀探測**或**真實小額試單**。

環境：`ccxt 4.5.63` 已安裝（`requirements.txt` 已列 `ccxt>=4.2.0`）。

---

## A. 已確認（無金鑰，ccxt.pro introspection，2026-07-02）

用 `ccxt.pro.bingx().has` 查得，全部為 `True`：

| 能力 | 結果 | 對 adapter 的意義 |
|------|------|-------------------|
| `watchOrders` | ✅ True | `stream_orders` 的 `watch_orders()` 可用，**不需**改 REST 輪詢回退 |
| `watchOHLCV` | ✅ True | `stream_candles` 的 `watch_ohlcv()` 可用 |
| `fetchPositions` | ✅ True | `fetch_positions` 恢復持倉可用 |
| `fetchOpenOrders` | ✅ True | `fetch_open_orders` 可用 |
| `setLeverage` | ✅ True | `setup_symbol` 可用 |
| `createStopOrder` | ✅ True | 支援止損觸發單 |
| `createOrderWithTakeProfitAndStopLoss` | ✅ True | 支援下單即附帶 TP/SL |

> 注意：**同步** `ccxt.bingx` 的 `has['watchOrders']` 是 `None`（watch* 是 pro 專屬），
> 查能力務必用 `ccxt.pro.bingx`，勿被同步版誤導。

BingX `swap.linear.createOrder` feature schema 另顯示支援：
`stopLoss`（nested：`triggerPriceType` last/mark/index + `price`）、`takeProfit`、
`triggerPrice`、`attachedStopLossTakeProfit`。

---

## B. 需唯讀探測確認（有 BingX 金鑰後跑 `python scripts/probe_ccxt.py`）

金鑰放 `secrets/bingx.txt` 或 env `BINGX_API_KEY` / `BINGX_API_SECRET`（唯讀即可，探測不下單）。

1. **可用餘額路徑** — adapter `get_available_capital` 讀 `bal["USDT"]["free"]`。
   探測印出 `bal.get("USDT",{}).get("free")`，核對非 None 且為預期數字。
2. **`fetch_positions` 結構** — adapter 取 `symbol / id / entryPrice / contracts`。
   有倉時核對這些 ccxt 統一欄位確實有值（無倉時 `[]`，只能之後有倉再驗）。
3. **`watch_ohlcv` 收盤判斷** — adapter 假設「回傳陣列、**倒數第二根** `ohlcv[-2]` = 已收盤」。
   探測印一根樣本，確認：回傳是完整陣列、最後一根是形成中、`[-2]` 取法正確。
   若 BingX 只回單根 / 帶收盤旗標，需改 `stream_candles` 邏輯。
4. **`watch_orders` 實際推送** — 探測等 10s。能力雖為 True，仍要確認真的吐訊息
   （多半需有活動訂單才會推）；並記錄 `status` 欄位實際值域，核對 adapter 的
   `_STATUS_MAP = {closed→FILLED, open→NEW, canceled→CANCELED}`。

---

## C. 仍需真實小額試單確認（唯讀探測無法涵蓋）

⚠️ 動真錢、不可逆，須本人最小數量 / 最低槓桿手動盯著做。

1. **止損下單參數形狀（最大不確定）** — adapter `place_sl` / `move_sl` 用
   `create_order(sym,"market","sell",None,None,{"stopLossPrice":px,"reduceOnly":True})`。
   BingX feature schema 偏好 nested `stopLoss` 形式，故 `stopLossPrice` 是否被正確解讀成
   獨立止損觸發單，**須用真實單驗**（下單回應是否 code 成功、實際掛出止損）。
   若不符，改用 `params={"stopLoss":{"triggerPrice":px}}` 或 `createStopOrder` 對應寫法。
2. **`move_sl` 撤舊掛新** — adapter 採 cancel 舊 SL + 新建。驗撤單成功、新單掛上。
3. **`place_entry` / `place_tp` 回應 id 路徑** — `_order_result` 取 `o["id"]`，真實回應核對。
4. **訂單狀態最終值** — 真實成交時 `watch_orders` 推的 `status` 是否落在 `_STATUS_MAP`，
   否則 `normalize_status` 會默默回 `"NEW"` 而漏判成交。

---

## D. 一句話狀態

能力面（websocket / 止損 API 是否存在）已用無金鑰方式**排除主要風險**；
剩下的是「欄位路徑」（需唯讀金鑰）與「止損參數形狀＋狀態值域」（需真實小額單）。
下一步：**取得 BingX 唯讀金鑰 → 跑 `probe_ccxt.py` → 校 B 段 → 再排真實小額單校 C 段。**
