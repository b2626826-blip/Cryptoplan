from __future__ import annotations
import asyncio

from loguru import logger
from models import Candle, OrderResult, OrderEvent, Position
from exchanges.base import Exchange, ExchangeError

_STATUS_MAP = {"closed": "FILLED", "open": "NEW", "canceled": "CANCELED"}


def normalize_status(raw_status: str) -> str:
    return _STATUS_MAP.get(str(raw_status).lower(), "NEW")


class CcxtAdapter(Exchange):
    def __init__(self, exchange_id: str, ex_cfg, client=None) -> None:
        self.name = exchange_id
        self.cfg = ex_cfg
        self.qty_step = float(getattr(ex_cfg, "qty_step", 0.0001))
        if client is None:
            import ccxt.pro as ccxtpro
            client = getattr(ccxtpro, exchange_id)({
                "apiKey": ex_cfg.api_key, "secret": ex_cfg.api_secret,
                "options": {"defaultType": "swap"}})
        self.client = client

    async def get_available_capital(self) -> float:
        bal = await self.client.fetch_balance()
        return float((bal.get("USDT") or {}).get("free", 0) or 0)

    async def setup_symbol(self, symbol, leverage) -> None:
        try:
            await self.client.set_leverage(leverage, symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{self.name}] set_leverage 失敗（可能已設）：{exc}")

    async def place_entry(self, symbol, qty, price, client_id) -> OrderResult:
        o = await self.client.create_order(
            symbol, "limit", "buy", qty, price,
            {"clientOrderId": client_id})
        return self._order_result(o)

    async def place_tp(self, symbol, qty, price, client_id) -> OrderResult:
        o = await self.client.create_order(
            symbol, "limit", "sell", qty, price,
            {"clientOrderId": client_id, "reduceOnly": True})
        return self._order_result(o)

    async def place_sl(self, symbol, position_id, sl_price) -> OrderResult:
        # ccxt 止損以 stop 參數帶入；確切參數依 Task 9 探測各家差異調整。
        o = await self.client.create_order(
            symbol, "market", "sell", None, None,
            {"stopLossPrice": sl_price, "reduceOnly": True})
        return self._order_result(o)

    async def move_sl(self, symbol, sl_ref, new_price) -> None:
        # ccxt 多數所無「改單」止損，採撤舊掛新。sl_ref 為舊單 id。
        await self.client.cancel_order(sl_ref, symbol)
        await self.client.create_order(
            symbol, "market", "sell", None, None,
            {"stopLossPrice": new_price, "reduceOnly": True})

    async def close_market(self, symbol, qty) -> None:
        await self.client.create_order(symbol, "market", "sell", qty, None,
                                       {"reduceOnly": True})

    async def cancel(self, symbol, order_ids) -> None:
        for oid in order_ids:
            if oid:
                await self.client.cancel_order(oid, symbol)

    async def fetch_positions(self) -> list[Position]:
        raw = await self.client.fetch_positions()
        out = []
        for p in raw:
            out.append(Position(
                symbol=p.get("symbol", ""), position_id=str(p.get("id") or ""),
                entry_price=float(p.get("entryPrice") or 0),
                qty=float(p.get("contracts") or 0), raw=p))
        return out

    async def fetch_open_orders(self, symbol) -> list[dict]:
        return await self.client.fetch_open_orders(symbol)

    async def stream_candles(self, subs, on_candle) -> None:
        async def watch_one(symbol, channel):
            tf = _channel_to_timeframe(channel)
            last_closed_ts = None
            while True:
                try:
                    ohlcv = await self.client.watch_ohlcv(symbol, tf)
                    # ccxt 回傳完整 K 棒陣列；倒數第二根視為已收盤
                    if len(ohlcv) >= 2:
                        ts, o, h, low, c, v = ohlcv[-2]
                        if ts != last_closed_ts:
                            last_closed_ts = ts
                            await on_candle(symbol, channel, Candle(
                                open_time=int(ts), open=o, high=h, low=low,
                                close=c, volume=v, closed=True))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"[{self.name}] watch_ohlcv 斷線：{exc}")
                    await asyncio.sleep(2)
        await asyncio.gather(*(watch_one(s, ch) for s, ch in subs))

    async def stream_orders(self, on_order) -> None:
        while True:
            try:
                orders = await self.client.watch_orders()
                for o in orders:
                    await on_order(OrderEvent(
                        order_id=str(o.get("id") or ""),
                        status=normalize_status(o.get("status")), raw=o))
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[{self.name}] watch_orders 斷線：{exc}")
                await asyncio.sleep(2)

    def _order_result(self, o: dict) -> OrderResult:
        oid = o.get("id")
        if not oid:
            raise ExchangeError("ccxt create_order 無 id", o)
        return OrderResult(order_id=str(oid), raw=o)


_CH_TF = {"market_kline_60min": "1h", "market_kline_1day": "1d",
          "market_kline_3day": "3d"}


def _channel_to_timeframe(channel: str) -> str:
    return _CH_TF.get(channel, "1h")
