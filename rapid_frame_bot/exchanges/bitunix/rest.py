from __future__ import annotations
import hashlib
import json
import time
import uuid
from typing import Any

import aiohttp
from loguru import logger

from config import Config

PROD_BASE = "https://fapi.bitunix.com"
API_PREFIX = "/api/v1/futures"


class BitunixREST:
    def __init__(self, config: Config, session: aiohttp.ClientSession) -> None:
        self.cfg = config
        self.session = session
        self.base = PROD_BASE

    # ---------- 純邏輯（可單元測試） ----------
    @staticmethod
    def sign(nonce: str, timestamp: str, api_key: str, query: str,
             body: str, secret: str) -> str:
        digest = hashlib.sha256(
            (nonce + timestamp + api_key + query + body).encode()
        ).hexdigest()
        return hashlib.sha256((digest + secret).encode()).hexdigest()

    @staticmethod
    def _build_query(params: dict[str, Any]) -> str:
        # Bitunix 簽名規格：query 依 ASCII key 升序，串接為 key+value（無 = 與 &）。
        # 例：{"id":1,"uid":200} -> "id1uid200"。
        return "".join(f"{k}{params[k]}" for k in sorted(params))

    # ---------- HTTP 核心 ----------
    async def _request(self, method: str, path: str,
                       params: dict | None = None,
                       body: dict | None = None) -> dict:
        params = params or {}
        query = self._build_query(params)
        body_str = json.dumps(body, separators=(",", ":")) if body else ""
        nonce = uuid.uuid4().hex
        ts = str(int(time.time() * 1000))
        sign = self.sign(nonce, ts, self.cfg.api_key, query, body_str,
                         self.cfg.api_secret)
        headers = {
            "api-key": self.cfg.api_key,
            "nonce": nonce,
            "timestamp": ts,
            "sign": sign,
            "Content-Type": "application/json",
        }
        url = self.base + API_PREFIX + path
        async with self.session.request(
            method, url, params=params or None,
            data=body_str or None, headers=headers
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                logger.error(f"REST {path} -> {resp.status}: {data}")
            return data

    # ---------- 市場 ----------
    async def get_trading_pairs(self) -> dict:
        return await self._request("GET", "/market/trading_pairs")

    async def get_tickers(self, symbols: list[str] | None = None) -> dict:
        params = {"symbols": ",".join(symbols)} if symbols else {}
        return await self._request("GET", "/market/tickers", params=params)

    async def get_klines(self, symbol: str, interval: str, limit: int = 50) -> dict:
        return await self._request("GET", "/market/kline",
                                   params={"symbol": symbol,
                                           "interval": interval,
                                           "limit": str(limit)})

    # ---------- 帳戶 ----------
    async def get_account(self, margin_coin: str = "USDT") -> dict:
        # 真實端點：GET /api/v1/futures/account?marginCoin=USDT（需 marginCoin）。
        return await self._request("GET", "/account",
                                   params={"marginCoin": margin_coin})

    async def change_leverage(self, symbol: str, leverage: int) -> dict:
        return await self._request("POST", "/account/change_leverage",
                                   body={"symbol": symbol, "leverage": leverage})

    async def change_margin_mode(self, symbol: str, mode: str) -> dict:
        return await self._request("POST", "/account/change_margin_mode",
                                   body={"symbol": symbol, "marginMode": mode})

    # ---------- 交易 ----------
    async def place_order(self, **body: Any) -> dict:
        return await self._request("POST", "/trade/place_order", body=body)

    async def cancel_orders(self, symbol: str, order_ids: list[str]) -> dict:
        return await self._request("POST", "/trade/cancel_orders",
                                   body={"symbol": symbol, "orderIds": order_ids})

    async def place_position_tpsl(self, **body: Any) -> dict:
        return await self._request(
            "POST", "/tp_sl/place_position_tp_sl_order", body=body)

    async def modify_position_tpsl(self, **body: Any) -> dict:
        return await self._request(
            "POST", "/tp_sl/modify_position_tp_sl_order", body=body)

    # ---------- 持倉 ----------
    async def get_pending_positions(self) -> dict:
        return await self._request("GET", "/position/get_pending_positions")

    async def get_pending_orders(self, symbol: str | None = None) -> dict:
        params = {"symbol": symbol} if symbol else {}
        return await self._request("GET", "/trade/get_pending_orders",
                                   params=params)
