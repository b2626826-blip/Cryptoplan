import pytest
from unittest.mock import AsyncMock, MagicMock
from models import OrderEvent, Position
from config import ExchangeConfig
from session import ExchangeSession


def _ex_cfg():
    return ExchangeConfig(
        name="bitunix", enabled=True, symbols=["BTCUSDT"],
        major_leverage=10, altcoin_leverage=5,
        major_timeframes=["1h", "3h"], altcoin_timeframes=["1d"],
        max_concurrent_positions=3, risk_per_trade=0.02, qty_step=0.001,
        api_key="k", api_secret="s", testnet=True)


def _session(testnet=True):
    ex = AsyncMock()
    ex.name = "bitunix"
    ex.qty_step = 0.001
    ex.fetch_positions.return_value = []
    ex.get_available_capital.return_value = 100.0
    return ExchangeSession(ex, _ex_cfg(), AsyncMock(), testnet=testnet), ex


@pytest.mark.asyncio
async def test_refresh_capital_uses_exchange():
    s, ex = _session()
    await s.refresh_capital()
    assert s.capital == 100.0
    ex.get_available_capital.assert_awaited_once()


def test_build_subscriptions_dedups_1h_3h():
    s, _ = _session()
    s.state_machines = s.build_state_machines()
    subs = s.build_subscriptions()
    # 1h 與 3h 共用 market_kline_60min，僅訂閱一次
    channels = [c for _, c in subs]
    assert channels.count("market_kline_60min") == 1


@pytest.mark.asyncio
async def test_route_order_only_filled_drives_state_machines():
    s, _ = _session()
    sm = AsyncMock()
    s.state_machines = {("BTCUSDT", "1h"): sm}
    await s.route_order(OrderEvent("OID", "NEW", {}))
    sm.on_order_filled.assert_not_awaited()
    await s.route_order(OrderEvent("OID", "FILLED", {}))
    sm.on_order_filled.assert_awaited_once_with("OID")
