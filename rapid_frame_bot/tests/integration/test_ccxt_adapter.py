import pytest
from unittest.mock import AsyncMock
from tests.contracts.exchange_contract import ExchangeContract
from exchanges.ccxt_based.adapter import CcxtAdapter, normalize_status


def _fake_client():
    c = AsyncMock()
    c.create_order.return_value = {"id": "OID"}
    c.fetch_balance.return_value = {"USDT": {"free": 300.0}}
    c.fetch_positions.return_value = [
        {"symbol": "BTC/USDT:USDT", "id": "p1", "entryPrice": 100.0,
         "contracts": 0.5, "info": {}}]
    c.fetch_open_orders.return_value = []
    return c


def _make():
    cfg = AsyncMock(qty_step=0.0001, symbols=["BTC/USDT:USDT"])
    return CcxtAdapter(exchange_id="bingx", ex_cfg=cfg, client=_fake_client())


class TestCcxtContract(ExchangeContract):
    def make_adapter(self):
        return _make()


@pytest.mark.parametrize("raw,expected", [
    ("closed", "FILLED"), ("open", "NEW"), ("canceled", "CANCELED"),
])
def test_normalize_status(raw, expected):
    assert normalize_status(raw) == expected


@pytest.mark.asyncio
async def test_capital_reads_usdt_free():
    assert await _make().get_available_capital() == 300.0


@pytest.mark.asyncio
async def test_fetch_positions_normalized():
    positions = await _make().fetch_positions()
    assert positions[0].position_id == "p1"
    assert positions[0].qty == 0.5
