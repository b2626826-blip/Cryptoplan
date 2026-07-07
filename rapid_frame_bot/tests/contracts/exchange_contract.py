"""Exchange 介面合約測試基底。子類別覆寫 make_adapter() 提供受測 adapter。
任何 adapter 都必須通過這組測試 —— 驗證正規化輸出符合介面約定。"""
import pytest
from models import OrderResult, OrderEvent, Position
from exchanges.base import Exchange


class ExchangeContract:
    def make_adapter(self) -> Exchange:
        raise NotImplementedError

    def test_is_exchange(self):
        assert isinstance(self.make_adapter(), Exchange)

    def test_has_name_and_qty_step(self):
        ex = self.make_adapter()
        assert isinstance(ex.name, str) and ex.name
        assert isinstance(ex.qty_step, float) and ex.qty_step > 0

    @pytest.mark.asyncio
    async def test_place_entry_returns_order_result(self):
        ex = self.make_adapter()
        r = await ex.place_entry("BTCUSDT", 0.01, 100.0, "cid1")
        assert isinstance(r, OrderResult)
        assert isinstance(r.order_id, str) and r.order_id

    @pytest.mark.asyncio
    async def test_fetch_positions_returns_normalized(self):
        ex = self.make_adapter()
        positions = await ex.fetch_positions()
        assert isinstance(positions, list)
        for p in positions:
            assert isinstance(p, Position)

    @pytest.mark.asyncio
    async def test_get_available_capital_is_float(self):
        ex = self.make_adapter()
        cap = await ex.get_available_capital()
        assert isinstance(cap, float)
