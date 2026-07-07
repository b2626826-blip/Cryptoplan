from __future__ import annotations
import time
from typing import Awaitable, Callable

from models import Candle, OrderResult, OrderEvent, Position
from exchanges.base import Exchange, ExchangeError
from exchanges.bitunix.rest import BitunixREST

_STATUS_MAP = {
    "FILLED": "FILLED",
    "PART_FILLED": "PARTIAL",
    "CANCELED": "CANCELED",
    "PART_FILLED_CANCELED": "CANCELED",
    "NEW": "NEW",
    "INIT": "NEW",
}


def normalize_status(raw_status: str) -> str:
    return _STATUS_MAP.get(str(raw_status).upper(), "NEW")


def _fmt(x: float) -> str:
    s = f"{x:.8f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-", "-0") else "0"


class BitunixAdapter(Exchange):
    name = "bitunix"

    def __init__(self, rest: BitunixREST, ws_factory: Callable,
                 qty_step: float = 0.001) -> None:
        self.rest = rest
        self._ws_factory = ws_factory  # 延後建立 WS（需 on_candle/on_order）
        self.qty_step = qty_step
        self._ws = None

    async def get_available_capital(self) -> float:
        acc = await self.rest.get_account()
        return float((acc.get("data") or {}).get("available", 0) or 0)

    async def setup_symbol(self, symbol: str, leverage: int) -> None:
        await self.rest.change_margin_mode(symbol, "CROSS")
        await self.rest.change_leverage(symbol, leverage)

    async def place_entry(self, symbol, qty, price, client_id) -> OrderResult:
        resp = await self.rest.place_order(
            symbol=symbol, side="BUY", qty=_fmt(qty), price=_fmt(price),
            tradeSide="OPEN", orderType="LIMIT", reduceOnly=False,
            effect="GTC", clientId=client_id)
        oid = (resp.get("data") or {}).get("orderId")
        if not oid:
            raise ExchangeError("place_entry 無 orderId", resp)
        return OrderResult(order_id=str(oid), raw=resp)

    async def place_tp(self, symbol, qty, price, client_id) -> OrderResult:
        resp = await self.rest.place_order(
            symbol=symbol, side="SELL", qty=_fmt(qty), price=_fmt(price),
            tradeSide="CLOSE", orderType="LIMIT", reduceOnly=True,
            effect="GTC", clientId=client_id)
        oid = (resp.get("data") or {}).get("orderId")
        if not oid:
            raise ExchangeError("place_tp 無 orderId", resp)
        return OrderResult(order_id=str(oid), raw=resp)

    async def place_sl(self, symbol, position_id, sl_price) -> OrderResult:
        resp = await self.rest.place_position_tpsl(
            symbol=symbol, positionId=position_id, slPrice=_fmt(sl_price),
            slStopType="MARK", slOrderType="MARKET")
        sid = (resp.get("data") or {}).get("tpslId")
        if not sid:
            raise ExchangeError("place_sl 無 tpslId", resp)
        return OrderResult(order_id=str(sid), raw=resp)

    async def move_sl(self, symbol, sl_ref, new_price) -> None:
        await self.rest.modify_position_tpsl(
            symbol=symbol, tpslId=sl_ref, slPrice=_fmt(new_price),
            slStopType="MARK", slOrderType="MARKET")

    async def close_market(self, symbol, qty) -> None:
        await self.rest.place_order(
            symbol=symbol, side="SELL", qty=_fmt(qty), tradeSide="CLOSE",
            orderType="MARKET", reduceOnly=True,
            clientId=f"close_{symbol}_{int(time.time())}")

    async def cancel(self, symbol, order_ids) -> None:
        if order_ids:
            await self.rest.cancel_orders(symbol, order_ids)

    async def fetch_positions(self) -> list[Position]:
        resp = await self.rest.get_pending_positions()
        out: list[Position] = []
        for pos in resp.get("data", []) or []:
            symbol = pos.get("symbol")
            if not symbol:
                continue
            out.append(Position(
                symbol=symbol,
                position_id=str(pos.get("positionId") or pos.get("positionID") or ""),
                entry_price=float(pos.get("avgOpenPrice") or pos.get("entryPrice") or 0),
                qty=float(pos.get("qty") or pos.get("positionAmt") or 0),
                raw=pos))
        return out

    async def fetch_open_orders(self, symbol) -> list[dict]:
        resp = await self.rest.get_pending_orders(symbol)
        odata = resp.get("data") or {}
        return odata.get("orderList", []) if isinstance(odata, dict) else (odata or [])

    # ---- 串流（Bitunix 雙連線，由 run_streams 單一入口帶起）----
    async def run_streams(self, subs, on_candle, on_order) -> None:
        """Bitunix 專用：單一入口同時帶起公開行情 + 私有訂單兩條 WS 連線。
        ExchangeSession 偵測到此方法時優先採用（見 base.supports_combined_stream）。"""
        async def order_cb(order_id: str, status: str) -> None:
            await on_order(OrderEvent(
                order_id=order_id, status=normalize_status(status),
                raw={"orderId": order_id, "orderStatus": status}))
        ws = self._ws_factory(on_candle=on_candle, on_order=order_cb)
        for symbol, channel in subs:
            ws.add_subscription(symbol, channel)
        self._ws = ws
        await ws.run()

    async def stream_candles(self, subs, on_candle) -> None:
        # combined 模式下不會被呼叫；保留可運作版本以滿足介面。
        await self.run_streams(subs, on_candle, self._noop_order)

    async def stream_orders(self, on_order) -> None:
        # combined 模式下不使用（訂單由 run_streams 一併帶起）。
        return

    async def _noop_order(self, *a) -> None:
        pass
