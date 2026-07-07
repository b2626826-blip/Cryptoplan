"""M5（開機恢復持倉）與 M7（本金刷新 + 零本金告警）的測試。
多交易所重構後，這些行為移入 ExchangeSession。"""
from unittest.mock import AsyncMock
import pytest

from config import ExchangeConfig
from models import Position
from session import ExchangeSession, _classify_orders
from strategy.state_machine import IN_POSITION


def _ex_cfg():
    return ExchangeConfig(
        name="bitunix", enabled=True, symbols=["BTCUSDT"],
        major_leverage=200, altcoin_leverage=20,
        major_timeframes=["1h", "3h"], altcoin_timeframes=["3h", "3d"],
        max_concurrent_positions=7, risk_per_trade=0.02, qty_step=0.001,
        api_key="K", api_secret="S", testnet=True)


def _session():
    ex = AsyncMock()
    ex.name = "bitunix"
    ex.qty_step = 0.001
    return ExchangeSession(ex, _ex_cfg(), AsyncMock(), testnet=True), ex


# ---------- M7：本金刷新 ----------

@pytest.mark.asyncio
async def test_refresh_capital_updates_value():
    s, ex = _session()
    ex.get_available_capital.return_value = 12345.6
    await s.refresh_capital()
    assert s.capital == pytest.approx(12345.6)
    s.notifier.send.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_capital_alerts_on_zero():
    s, ex = _session()
    ex.get_available_capital.return_value = 0.0
    await s.refresh_capital()
    assert s.capital == 0
    s.notifier.send.assert_awaited_once()


# ---------- M5：訂單分類 ----------

def test_classify_orders_sorts_tps_and_finds_sl():
    orders = [
        {"orderId": "TP2", "orderType": "LIMIT", "side": "SELL",
         "reduceOnly": True, "price": "120"},
        {"orderId": "TP1", "orderType": "LIMIT", "side": "SELL",
         "reduceOnly": True, "price": "80"},
        {"orderId": "TP3", "orderType": "LIMIT", "side": "SELL",
         "reduceOnly": True, "price": "200"},
        {"orderId": "SL1", "orderType": "STOP_MARKET", "side": "SELL",
         "reduceOnly": True, "price": "50"},
    ]
    tp_ids, sl_id = _classify_orders(orders)
    assert tp_ids == ["TP1", "TP2", "TP3"]   # 依價格升序
    assert sl_id == "SL1"


def test_classify_orders_handles_no_sl():
    orders = [
        {"orderId": "TP1", "orderType": "LIMIT", "side": "SELL",
         "reduceOnly": True, "price": "80"},
    ]
    tp_ids, sl_id = _classify_orders(orders)
    assert tp_ids == ["TP1"]
    assert sl_id is None


# ---------- M5：恢復持倉 ----------

@pytest.mark.asyncio
async def test_recover_positions_restores_in_position():
    s, ex = _session()
    ex.fetch_positions.return_value = [
        Position(symbol="BTCUSDT", position_id="POS9",
                 entry_price=98000.0, qty=0.2, raw={})]
    ex.fetch_open_orders.return_value = [
        {"orderId": "TP1", "orderType": "LIMIT", "side": "SELL",
         "reduceOnly": True, "price": "110000"},
        {"orderId": "SL1", "orderType": "STOP_MARKET", "side": "SELL",
         "reduceOnly": True, "price": "96000"},
    ]
    s.state_machines = s.build_state_machines()
    await s.recover_positions()

    sm = s.state_machines[("BTCUSDT", "1h")]   # 主要時框
    assert sm.state == IN_POSITION
    assert sm.position is not None
    assert sm.position.position_id == "POS9"
    assert sm.position.entry_price == pytest.approx(98000)
    assert sm.position.total_qty == pytest.approx(0.2)
    assert sm.position.tpsl_id == "SL1"
    assert sm.position.tp_order_ids == ["TP1"]
    assert s.shared.has_position("BTCUSDT") is True


@pytest.mark.asyncio
async def test_recover_positions_empty_does_nothing():
    s, ex = _session()
    ex.fetch_positions.return_value = []
    s.state_machines = s.build_state_machines()
    await s.recover_positions()
    assert s.shared.has_position("BTCUSDT") is False
