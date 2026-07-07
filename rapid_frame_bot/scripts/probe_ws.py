"""Bitunix 公開 WebSocket 行情探測工具（唯讀、無需簽名、不下單）。

用途：在有網路的機器上驗證真實行情管道與訊息格式，並比對本專案
`api/ws.py` 的 `parse_kline_message` 是否與交易所實際回應一致。

執行（從 rapid_frame_bot/ 目錄）：
    python scripts/probe_ws.py
    python scripts/probe_ws.py --symbol ETHUSDT --channel market_kline_60min --count 10

安全：只訂閱公開行情、印出收到的原始訊息，不送任何下單請求。
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

# 讓本腳本可從專案根（rapid_frame_bot/）匯入模組
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets  # noqa: E402
from exchanges.bitunix.ws import CHANNEL_MAP, parse_kline_message  # noqa: E402

# 經實測確認：正確的 Futures 公開 WS 網址為 wss://fapi.bitunix.com/public/
# （技術文件原填的 fstream.bitunix.com 為不存在的網域）。
PUBLIC_URL = "wss://fapi.bitunix.com/public/"

URL_CANDIDATES = [
    "wss://fapi.bitunix.com/public/",
]


async def _try_connect(url: str, symbol: str, channel: str, count: int,
                       timeout: float) -> int:
    sub = {"op": "subscribe", "args": [{"symbol": symbol, "ch": channel}]}
    print(f"連線中：{url}")
    try:
        async with websockets.connect(url, open_timeout=15) as ws:
            print("✓ 連線成功")
            await ws.send(json.dumps(sub))
            print(f"→ 已送訂閱：{json.dumps(sub)}")
            print("=" * 70)
            n = 0
            while n < count:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except asyncio.TimeoutError:
                    print(f"({timeout:.0f} 秒內無更多訊息，結束)")
                    break
                n += 1
                text = raw if isinstance(raw, str) else raw.decode("utf-8", "ignore")
                print(f"[原始 #{n}] {text[:400]}")
                try:
                    msg = json.loads(text)
                except Exception:
                    print("        （非 JSON，可能是 ping/pong）")
                    continue
                # 解析器目前可能與真實格式不符；包起來避免中斷探測
                try:
                    parsed = parse_kline_message(msg)
                except Exception as exc:  # noqa: BLE001
                    print(f"        · 解析器丟出 {type(exc).__name__}: {exc}"
                          f"（keys={list(msg.keys())}）— 需依真實格式修正")
                    continue
                if parsed:
                    sym, ch, candle = parsed
                    print(f"        ✓ 解析成功: {sym} {ch} "
                          f"O={candle.open} H={candle.high} L={candle.low} "
                          f"C={candle.close} closed={candle.closed}")
                else:
                    print(f"        · 回 None（keys={list(msg.keys())}）")
            print("=" * 70)
            print(f"共收到 {n} 則訊息")
            return 0
    except Exception as exc:  # noqa: BLE001
        print(f"✗ 失敗：{type(exc).__name__}: {exc}")
        print("  常見原因：無網路、防火牆阻擋 wss、或官方 URL 已變更。")
        return 1


async def run(symbol: str, channel: str, count: int, timeout: float,
              url: str | None) -> int:
    urls = [url] if url else URL_CANDIDATES
    for u in urls:
        code = await _try_connect(u, symbol, channel, count, timeout)
        if code == 0:
            print(f"\n★ 可用的 WebSocket 網址：{u}")
            print("  → 把這個網址貼回給我，我會更新 api/ws.py 與 main.py。")
            return 0
        print("-" * 70)
    print("\n所有候選網址都連不上。請查 Bitunix 官方 API 文件取得正確的")
    print("Futures 公開 WebSocket 網址，再用 --url 指定：")
    print("  python scripts/probe_ws.py --url wss://<正確網址>")
    return 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Bitunix 公開 WS 行情探測")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--channel", default=CHANNEL_MAP["1h"],
                    help="預設 market_kline_60min（1h）")
    ap.add_argument("--count", type=int, default=8, help="收幾則訊息後結束")
    ap.add_argument("--timeout", type=float, default=20.0,
                    help="單則訊息等待秒數")
    ap.add_argument("--url", default=None,
                    help="覆寫 WS 網址（官方文件查到的正確網址）")
    args = ap.parse_args()
    code = asyncio.run(run(args.symbol, args.channel, args.count,
                           args.timeout, args.url))
    sys.exit(code)


if __name__ == "__main__":
    main()
