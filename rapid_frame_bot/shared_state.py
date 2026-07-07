from __future__ import annotations


class SharedState:
    """跨週期共享：持倉鎖、持倉計數、每日訊號計數。asyncio 單執行緒，無需鎖。"""

    def __init__(self, max_positions: int) -> None:
        self.max_positions = max_positions
        self.active_positions: dict[str, bool] = {}
        self.daily_signal_count: int = 0

    def active_position_count(self) -> int:
        return sum(1 for v in self.active_positions.values() if v)

    def can_open(self) -> bool:
        return self.active_position_count() < self.max_positions

    def has_position(self, symbol: str) -> bool:
        return self.active_positions.get(symbol, False)

    def mark_open(self, symbol: str) -> None:
        self.active_positions[symbol] = True

    def mark_closed(self, symbol: str) -> None:
        self.active_positions[symbol] = False

    def record_signal(self) -> None:
        self.daily_signal_count += 1

    def reset_daily(self) -> None:
        self.daily_signal_count = 0
