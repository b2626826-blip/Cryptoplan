import pytest
from unittest.mock import AsyncMock
from config import ExchangeConfig
from session import ExchangeSession


def _cfg(name, qty_step):
    return ExchangeConfig(
        name=name, enabled=True, symbols=["BTCUSDT"],
        major_leverage=10, altcoin_leverage=5,
        major_timeframes=["1h"], altcoin_timeframes=[],
        max_concurrent_positions=3, risk_per_trade=0.02, qty_step=qty_step,
        api_key="k", api_secret="s", testnet=True)


@pytest.mark.asyncio
async def test_two_paper_sessions_independent_capital():
    ex1, ex2 = AsyncMock(), AsyncMock()
    ex1.name, ex2.name = "bitunix", "bingx"
    ex1.qty_step, ex2.qty_step = 0.001, 0.0001
    ex1.get_available_capital.return_value = 100.0
    ex2.get_available_capital.return_value = 500.0
    s1 = ExchangeSession(ex1, _cfg("bitunix", 0.001), AsyncMock(), testnet=True)
    s2 = ExchangeSession(ex2, _cfg("bingx", 0.0001), AsyncMock(), testnet=True)
    await s1.refresh_capital()
    await s2.refresh_capital()
    # 各家資金獨立、互不干擾
    assert s1.capital == 100.0 and s2.capital == 500.0
    # paper_sim 各自獨立
    assert s1.paper_sim is not s2.paper_sim
    # shared_state 各自獨立
    s1.shared.mark_open("BTCUSDT")
    assert s1.shared.has_position("BTCUSDT")
    assert not s2.shared.has_position("BTCUSDT")
