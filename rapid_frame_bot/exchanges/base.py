from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from models import Candle, OrderResult, OrderEvent, Position


class ExchangeError(Exception):
    """交易所邊界例外：原始回應無法正規化、API 失敗等。附 raw 以利除錯。"""

    def __init__(self, message: str, raw: object = None) -> None:
        super().__init__(message)
        self.raw = raw


class Exchange(ABC):
    """所有交易所 adapter 的統一介面。方法皆已正規化，策略層不需懂任一家格式。"""

    name: str
    qty_step: float

    # ---- 帳戶/設定 ----
    @abstractmethod
    async def get_available_capital(self) -> float: ...

    @abstractmethod
    async def setup_symbol(self, symbol: str, leverage: int) -> None: ...

    # ---- 下單（語意化）----
    @abstractmethod
    async def place_entry(self, symbol: str, qty: float, price: float,
                          client_id: str) -> OrderResult: ...

    @abstractmethod
    async def place_tp(self, symbol: str, qty: float, price: float,
                       client_id: str) -> OrderResult: ...

    @abstractmethod
    async def place_sl(self, symbol: str, position_id: str,
                       sl_price: float) -> OrderResult: ...

    @abstractmethod
    async def move_sl(self, symbol: str, sl_ref: str, new_price: float) -> None: ...

    @abstractmethod
    async def close_market(self, symbol: str, qty: float) -> None: ...

    @abstractmethod
    async def cancel(self, symbol: str, order_ids: list[str]) -> None: ...

    # ---- 開機恢復（已正規化）----
    @abstractmethod
    async def fetch_positions(self) -> list[Position]: ...

    @abstractmethod
    async def fetch_open_orders(self, symbol: str) -> list[dict]: ...

    # ---- 串流 ----
    @abstractmethod
    async def stream_candles(
        self, subs: list[tuple[str, str]],
        on_candle: Callable[[str, str, Candle], Awaitable[None]]) -> None: ...

    @abstractmethod
    async def stream_orders(
        self, on_order: Callable[[OrderEvent], Awaitable[None]]) -> None: ...

    def supports_combined_stream(self) -> bool:
        """True 表示 adapter 提供 run_streams() 單一入口（如 Bitunix 雙連線）。
        ccxt adapter 回傳 False，由 session 分別 await stream_candles/stream_orders。"""
        return hasattr(self, "run_streams")
