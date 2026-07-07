from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    closed: bool = True


@dataclass
class FiboLevels:
    fib_low: float
    fib_high: float
    sl: float
    entry: float
    tp1: float
    tp2: float
    tp3: float


@dataclass
class PatternContext:
    c1: Candle
    c2: Candle
    c3: Candle
    c4: Candle
    fibo: FiboLevels
    entry_order_id: str | None = None
    entry_client_id: str | None = None


@dataclass
class PositionContext:
    symbol: str
    timeframe: str
    position_id: str
    entry_price: float
    total_qty: float
    tpsl_id: str | None
    tp_order_ids: list[str] = field(default_factory=list)
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    fibo: FiboLevels | None = None


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    raw: dict


@dataclass(frozen=True)
class OrderEvent:
    order_id: str
    status: str  # 正規化：FILLED / PARTIAL / CANCELED / NEW
    raw: dict


@dataclass(frozen=True)
class Position:
    symbol: str
    position_id: str
    entry_price: float
    qty: float
    raw: dict
