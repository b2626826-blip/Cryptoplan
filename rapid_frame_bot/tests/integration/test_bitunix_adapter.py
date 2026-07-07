import pytest
from tests.contracts.exchange_contract import ExchangeContract
from exchanges.bitunix.adapter import BitunixAdapter, normalize_status


class FakeRest:
    """以實測真實回應形狀回傳的假 REST。"""
    async def place_order(self, **kw):
        return {"data": {"orderId": "OID123"}}
    async def place_position_tpsl(self, **kw):
        return {"data": {"tpslId": "TP1"}}
    async def cancel_orders(self, symbol, order_ids):
        return {"data": {}}
    async def modify_position_tpsl(self, **kw):
        return {"data": {}}
    async def get_account(self, margin_coin="USDT"):
        return {"data": {"available": "250.5"}}
    async def change_margin_mode(self, symbol, mode):
        return {"data": {}}
    async def change_leverage(self, symbol, leverage):
        return {"data": {}}
    async def get_pending_positions(self):
        return {"data": [{"symbol": "BTCUSDT", "positionId": "p1",
                          "avgOpenPrice": "100", "qty": "0.5"}]}
    async def get_pending_orders(self, symbol=None):
        return {"data": {"total": 0, "orderList": []}}


def _make():
    return BitunixAdapter(rest=FakeRest(), ws_factory=lambda *a, **k: None,
                          qty_step=0.001)


class TestBitunixContract(ExchangeContract):
    def make_adapter(self):
        return _make()


@pytest.mark.parametrize("raw,expected", [
    ("FILLED", "FILLED"),
    ("PART_FILLED", "PARTIAL"),
    ("CANCELED", "CANCELED"),
    ("PART_FILLED_CANCELED", "CANCELED"),
    ("NEW", "NEW"),
    ("INIT", "NEW"),
])
def test_normalize_status(raw, expected):
    assert normalize_status(raw) == expected


@pytest.mark.asyncio
async def test_fetch_positions_maps_bitunix_fields():
    ex = _make()
    positions = await ex.fetch_positions()
    assert positions[0].symbol == "BTCUSDT"
    assert positions[0].position_id == "p1"
    assert positions[0].entry_price == 100.0
    assert positions[0].qty == 0.5


@pytest.mark.asyncio
async def test_get_available_capital_parses_nested():
    ex = _make()
    assert await ex.get_available_capital() == 250.5
