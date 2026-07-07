from __future__ import annotations
from dataclasses import dataclass

from loguru import logger
from models import Candle

HIGH = "high"  # 當 candle.high >= price 成交
LOW = "low"    # 當 candle.low <= price 成交


@dataclass
class PaperOrder:
    order_id: str
    symbol: str
    price: float
    trigger: str   # HIGH 或 LOW
    priority: int  # 數字小者於同一根 K 棒中先成交


class PaperFillSimulator:
    """追蹤紙上訂單，依每根收盤 K 棒的 OHLC 判斷哪一筆成交。
    每次 check() 至多回傳一筆，呼叫端用迴圈直到 None，
    以解析同一根 K 棒上的鏈式成交（進場 → TP）。"""

    def __init__(self) -> None:
        self._orders: dict[str, PaperOrder] = {}

    def register(self, order_id: str, symbol: str, price: float,
                 trigger: str, priority: int) -> None:
        self._orders[order_id] = PaperOrder(order_id, symbol, price,
                                            trigger, priority)

    def unregister(self, order_id: str) -> None:
        self._orders.pop(order_id, None)

    def update_price(self, order_id: str, price: float) -> None:
        o = self._orders.get(order_id)
        if o is not None:
            o.price = price

    def check(self, symbol: str, candle: Candle) -> str | None:
        """回傳此 K 棒觸發的、優先序最高的單一訂單 id（並移除）。
        無觸發回傳 None。"""
        candidates: list[PaperOrder] = []
        for o in self._orders.values():
            if o.symbol != symbol:
                continue
            if o.trigger == HIGH and candle.high >= o.price:
                candidates.append(o)
            elif o.trigger == LOW and candle.low <= o.price:
                candidates.append(o)
        if not candidates:
            return None
        winner = min(candidates, key=lambda o: o.priority)
        self.unregister(winner.order_id)
        logger.info(f"[PAPER] fill {winner.order_id} {symbol} @ {winner.price}")
        return winner.order_id
