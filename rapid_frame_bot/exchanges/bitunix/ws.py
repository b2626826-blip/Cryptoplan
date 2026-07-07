from __future__ import annotations
import asyncio
import hashlib
import json
import time
import uuid
from typing import Awaitable, Callable

import websockets
from loguru import logger
from models import Candle

CHANNEL_MAP: dict[str, str] = {
    "1h": "market_kline_60min",
    "3h": "market_kline_60min",
    "1d": "market_kline_1day",
    "3d": "market_kline_3day",
}
_KLINE_CHANNELS = set(CHANNEL_MAP.values())

# 各頻道週期長度（毫秒），用於由 ts 推導 K 棒所屬時間桶與收盤偵測。
INTERVAL_MS: dict[str, int] = {
    "market_kline_60min": 3_600_000,
    "market_kline_1day": 86_400_000,
    "market_kline_3day": 259_200_000,
}


def parse_kline_message(msg: dict) -> tuple[str, str, Candle] | None:
    """解析 Bitunix 公開 K 線推送。

    實測真實格式（非技術文件假設）：頂層 `ts`（伺服器時間，毫秒），
    `data` 內為 `o/h/l/c`（價格字串）、`b`（基礎成交量）、`q`（計價額）。
    **無 `t`、無 `v`、無 `closed` 旗標**——每則都是「當前正在形成的 K 棒」
    完整快照，收盤需由 KlineCloseDetector 依時間桶滾動判斷。

    回傳的 candle.closed 一律為 False；open_time 暫存頂層 ts（對齊由
    KlineCloseDetector 處理）。
    """
    ch = msg.get("ch")
    if (ch not in _KLINE_CHANNELS or "data" not in msg
            or "symbol" not in msg or "ts" not in msg):
        return None
    d = msg["data"]
    candle = Candle(
        open_time=int(msg["ts"]),
        open=float(d["o"]), high=float(d["h"]), low=float(d["l"]),
        close=float(d["c"]), volume=float(d.get("b", 0) or 0),
        closed=False,
    )
    return (msg["symbol"], ch, candle)


class KlineCloseDetector:
    """將 Bitunix 的「持續推送當前 K 棒」轉為「收盤事件」。

    Bitunix 不送收盤旗標：同一週期內每隔約 2 秒推一次當前 K 棒快照，
    跨入新週期時上一根即已收盤。本偵測器追蹤每個 (symbol, channel) 的
    當前時間桶與最後一個 tick，桶跳號時回傳上一根（標記 closed=True、
    open_time 對齊桶起點）。
    """

    def __init__(self) -> None:
        # (symbol, channel) -> (bucket, 最後一個 tick candle)
        self._cur: dict[tuple[str, str], tuple[int, Candle]] = {}

    def on_tick(self, symbol: str, channel: str,
                tick: Candle) -> Candle | None:
        interval = INTERVAL_MS.get(channel)
        if interval is None:
            return None
        bucket = tick.open_time // interval
        key = (symbol, channel)
        prev = self._cur.get(key)
        self._cur[key] = (bucket, tick)
        if prev is None or prev[0] == bucket:
            return None
        prev_bucket, prev_tick = prev
        return Candle(
            open_time=prev_bucket * interval,
            open=prev_tick.open, high=prev_tick.high, low=prev_tick.low,
            close=prev_tick.close, volume=prev_tick.volume, closed=True,
        )


def parse_order_message(msg: dict) -> tuple[str, str] | None:
    """解析私有 WS 訂單頻道推送（ch=="order"）。

    實測真實格式：`data` 內狀態欄位為 **`orderStatus`**（非 `status`），
    值如 INIT/NEW/PART_FILLED/CANCELED/FILLED/PART_FILLED_CANCELED；
    另有 `event`（CREATE/UPDATE/CLOSE）。保留 `status` 後備以相容。
    """
    if msg.get("ch") != "order" or "data" not in msg:
        return None
    d = msg["data"]
    oid = d.get("orderId")
    status = d.get("orderStatus") or d.get("status")
    if not oid or not status:
        return None
    return (str(oid), str(status))


class BitunixWS:
    def __init__(self, public_url: str, private_url: str,
                 on_candle: Callable[[str, str, Candle], Awaitable[None]],
                 on_order: Callable[[str, str], Awaitable[None]],
                 api_key: str = "", api_secret: str = "") -> None:
        self.public_url = public_url
        self.private_url = private_url
        self.on_candle = on_candle
        self.on_order = on_order
        self.api_key = api_key
        self.api_secret = api_secret
        self.subscriptions: list[dict] = []
        self.close_detector = KlineCloseDetector()

    def add_subscription(self, symbol: str, channel: str) -> None:
        self.subscriptions.append({"symbol": symbol, "ch": channel})

    # ---------- 私有 WS 認證（純邏輯，可單元測試） ----------
    @staticmethod
    def sign_login(nonce: str, timestamp: str, api_key: str,
                   secret: str) -> str:
        """私有 WS 登入簽名。

        注意：公式與 REST 不同——第一層只雜湊 `nonce+timestamp+apiKey`
        （無 query、無 body）：
            digest = SHA256(nonce + timestamp + apiKey)
            sign   = SHA256(digest + secretKey)
        """
        digest = hashlib.sha256(
            (nonce + timestamp + api_key).encode()).hexdigest()
        return hashlib.sha256((digest + secret).encode()).hexdigest()

    @classmethod
    def build_login(cls, api_key: str, secret: str) -> dict:
        """組出 {"op":"login","args":[{apiKey,timestamp,nonce,sign}]}。"""
        nonce = uuid.uuid4().hex
        ts = str(int(time.time() * 1000))
        sign = cls.sign_login(nonce, ts, api_key, secret)
        return {"op": "login", "args": [{
            "apiKey": api_key, "timestamp": ts, "nonce": nonce, "sign": sign}]}

    async def run(self) -> None:
        """同時維護公開行情與私有訂單兩條連線（各自獨立重連）。"""
        tasks = [self._run_public()]
        if self.api_key and self.api_secret:
            tasks.append(self._run_private())
        else:
            logger.info("未設定 API 金鑰，略過私有 WS（訂單回報）。")
        await asyncio.gather(*tasks)

    async def _run_public(self) -> None:
        backoff = 1
        while True:
            try:
                async with websockets.connect(self.public_url) as ws:
                    await self._subscribe(ws)
                    backoff = 1
                    async for raw in ws:
                        try:
                            await self._dispatch(json.loads(raw))
                        except Exception as exc:  # noqa: BLE001
                            logger.error(f"行情訊息處理失敗（已略過）：{exc}")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"公開 WS 斷線：{exc}，{backoff}s 後重連")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _run_private(self) -> None:
        backoff = 1
        while True:
            try:
                async with websockets.connect(self.private_url) as ws:
                    backoff = 1
                    async for raw in ws:
                        try:
                            await self._dispatch_private(ws, json.loads(raw))
                        except Exception as exc:  # noqa: BLE001
                            logger.error(f"訂單訊息處理失敗（已略過）：{exc}")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"私有 WS 斷線：{exc}，{backoff}s 後重連")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _subscribe(self, ws) -> None:
        if self.subscriptions:
            await ws.send(json.dumps({"op": "subscribe",
                                      "args": self.subscriptions}))

    async def _dispatch(self, msg: dict) -> None:
        kline = parse_kline_message(msg)
        if kline:
            symbol, ch, tick = kline
            # tick 為當前形成中的 K 棒；跨週期才會收盤
            closed = self.close_detector.on_tick(symbol, ch, tick)
            if closed is not None:
                await self.on_candle(symbol, ch, closed)
            return
        order = parse_order_message(msg)
        if order:
            await self.on_order(*order)

    async def _dispatch_private(self, ws, msg: dict) -> None:
        """私有連線分派：connect→登入並訂閱、ping→pong、order→回呼。

        實測：伺服器連上先送 {"op":"connect",...}，登入後**不回 login 回執**，
        故收到 connect 即送 login 並立刻訂閱 order 頻道（不等回執）。
        """
        op = msg.get("op")
        if op == "connect":
            await ws.send(json.dumps(
                self.build_login(self.api_key, self.api_secret)))
            await ws.send(json.dumps({"op": "subscribe", "args": ["order"]}))
            logger.info("私有 WS：已送登入並訂閱 order 頻道")
            return
        if op == "login" and not (msg.get("data", {}) or {}).get("result", True):
            logger.error(f"私有 WS 登入被拒：{msg}")
            return
        if op == "ping":
            await ws.send(json.dumps({"op": "pong", "pong": msg.get("ping")}))
            return
        order = parse_order_message(msg)
        if order:
            await self.on_order(*order)
