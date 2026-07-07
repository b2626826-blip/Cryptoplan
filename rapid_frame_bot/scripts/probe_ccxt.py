"""唯讀探測 ccxt 對 BingX 合約的行為。從 secrets/bingx.txt 或 env 取金鑰，不下單。
用途：在實作 CcxtAdapter 前，確認以下事實（呼應 spec 風險項）：
  1. fetch_balance 的 USDT 可用餘額路徑
  2. fetch_positions 回傳結構
  3. watch_ohlcv 是否帶收盤旗標（決定要不要 KlineCloseDetector 等價物）
  4. watch_orders 私有訂單推送是否可用、status 欄位值域
執行：python scripts/probe_ccxt.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ccxt.pro as ccxtpro  # noqa: E402
from config_secrets import load_keys  # noqa: E402


async def main():
    api_key, api_secret = load_keys("bingx")
    if not api_key:
        print("缺少 BingX 金鑰（env BINGX_API_KEY 或 secrets/bingx.txt）")
        sys.exit(1)
    ex = ccxtpro.bingx({
        "apiKey": api_key, "secret": api_secret,
        "options": {"defaultType": "swap"},
    })
    try:
        bal = await ex.fetch_balance()
        print("USDT 可用：", bal.get("USDT", {}).get("free"))
        positions = await ex.fetch_positions()
        print("持倉數：", len(positions))
        # 收一根 K 線觀察結構
        ohlcv = await ex.watch_ohlcv("BTC/USDT:USDT", "1h")
        print("watch_ohlcv 樣本：", ohlcv[-1] if ohlcv else None)
        # 觀察私有訂單推送是否可用（10 秒）
        try:
            orders = await asyncio.wait_for(ex.watch_orders(), timeout=10)
            print("watch_orders 可用，樣本：", orders[:1])
        except asyncio.TimeoutError:
            print("watch_orders 10s 無推送（可能需有活動訂單才會吐）")
    finally:
        await ex.close()


if __name__ == "__main__":
    asyncio.run(main())
