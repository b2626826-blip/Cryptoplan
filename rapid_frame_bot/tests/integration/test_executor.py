from unittest.mock import AsyncMock, MagicMock
import pytest
from models import OrderResult, FiboLevels
from trader.executor import Executor


def _cfg(testnet: bool):
    return MagicMock(testnet=testnet)


def _fibo():
    return FiboLevels(fib_low=100, fib_high=110, sl=138, entry=158,
                      tp1=218, tp2=258, tp3=358)


def _live_exchange():
    ex = AsyncMock()
    ex.place_entry.return_value = OrderResult("OID1", {})
    ex.place_tp.side_effect = [OrderResult("TP1", {}), OrderResult("TP2", {}),
                               OrderResult("TP3", {})]
    ex.place_sl.return_value = OrderResult("T1", {})
    return ex


@pytest.mark.asyncio
async def test_place_entry_live_returns_order_id():
    ex = _live_exchange()
    execu = Executor(ex, _cfg(testnet=False), AsyncMock())
    oid = await execu.place_entry("BTCUSDT", 0.2, 158.0, "cid1")
    assert oid == "OID1"
    ex.place_entry.assert_awaited_once_with("BTCUSDT", 0.2, 158.0, "cid1")


@pytest.mark.asyncio
async def test_place_entry_testnet_skips_exchange():
    ex = AsyncMock()
    execu = Executor(ex, _cfg(testnet=True), AsyncMock())
    oid = await execu.place_entry("BTCUSDT", 0.2, 158.0, "cid1")
    ex.place_entry.assert_not_awaited()
    assert oid is not None  # paper order id


@pytest.mark.asyncio
async def test_on_entry_filled_sets_sl_and_three_tps():
    ex = _live_exchange()
    notifier = AsyncMock()
    execu = Executor(ex, _cfg(testnet=False), notifier)
    out = await execu.on_entry_filled("BTCUSDT", "POS1", 1.0, 158.0, _fibo())
    assert out["tpsl_id"] == "T1"
    assert out["tp_order_ids"] == ["TP1", "TP2", "TP3"]
    assert ex.place_sl.await_count == 1
    assert ex.place_tp.await_count == 3
    # TP quantities 0.30, 0.30, 0.28
    qtys = [c.args[1] for c in ex.place_tp.call_args_list]
    assert qtys == [pytest.approx(0.30), pytest.approx(0.30), pytest.approx(0.28)]
    notifier.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_remaining_market_and_cancel_sl():
    ex = AsyncMock()
    execu = Executor(ex, _cfg(testnet=False), AsyncMock())
    await execu.close_remaining("BTCUSDT", "POS1", 0.12, "T1")
    ex.close_market.assert_awaited_once_with("BTCUSDT", 0.12)
    ex.cancel.assert_awaited_once_with("BTCUSDT", ["T1"])  # 取消保本止損


@pytest.mark.asyncio
async def test_cancel_entry_calls_exchange_cancel():
    ex = AsyncMock()
    execu = Executor(ex, _cfg(testnet=False), AsyncMock())
    await execu.cancel_entry("BTCUSDT", "OID1")
    ex.cancel.assert_awaited_once_with("BTCUSDT", ["OID1"])


@pytest.mark.asyncio
async def test_paper_place_entry_registers_in_sim():
    from trader.paper_sim import PaperFillSimulator
    sim = PaperFillSimulator()
    execu = Executor(AsyncMock(), _cfg(testnet=True), AsyncMock(), paper_sim=sim)
    pid = await execu.place_entry("BTCUSDT", 0.2, 158.0, "cid1")
    from models import Candle
    candle = Candle(open_time=0, open=158, high=159, low=157, close=158, volume=1)
    assert sim.check("BTCUSDT", candle) == pid   # high>=158 觸發進場


@pytest.mark.asyncio
async def test_paper_on_entry_filled_registers_sl_and_tps():
    from trader.paper_sim import PaperFillSimulator
    sim = PaperFillSimulator()
    execu = Executor(AsyncMock(), _cfg(testnet=True), AsyncMock(), paper_sim=sim)
    out = await execu.on_entry_filled("BTCUSDT", "POS1", 1.0, 158.0, _fibo())
    from models import Candle
    # 一根觸及 tp1(218) 的 K 棒應回傳 tp1 id（SL 138 未觸）
    hit = Candle(open_time=0, open=158, high=220, low=150, close=219, volume=1)
    fid = sim.check("BTCUSDT", hit)
    assert fid == out["tp_order_ids"][0]
