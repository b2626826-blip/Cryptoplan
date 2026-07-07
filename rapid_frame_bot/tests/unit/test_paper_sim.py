from models import Candle
from trader.paper_sim import PaperFillSimulator, HIGH, LOW


def c(high, low, close=None):
    cl = close if close is not None else (high + low) / 2
    return Candle(open_time=0, open=cl, high=high, low=low, close=cl, volume=1.0)


def test_high_trigger_fills_when_price_reaches():
    s = PaperFillSimulator()
    s.register("E1", "BTC", 100.0, HIGH, 1)
    assert s.check("BTC", c(high=99, low=90)) is None     # 未觸及
    assert s.check("BTC", c(high=101, low=95)) == "E1"    # high>=100 成交
    assert s.check("BTC", c(high=200, low=1)) is None     # 已移除


def test_low_trigger_fills_when_price_drops():
    s = PaperFillSimulator()
    s.register("SL", "BTC", 90.0, LOW, 0)
    assert s.check("BTC", c(high=110, low=95)) is None    # 未跌破
    assert s.check("BTC", c(high=110, low=89)) == "SL"    # low<=90 成交


def test_priority_sl_before_tp_same_candle():
    s = PaperFillSimulator()
    s.register("TP1", "BTC", 105.0, HIGH, 2)
    s.register("SL", "BTC", 95.0, LOW, 0)
    # 一根大 K 棒同時觸 TP1(high>=105) 與 SL(low<=95)；SL 優先序 0 先成交
    assert s.check("BTC", c(high=106, low=94)) == "SL"
    assert s.check("BTC", c(high=106, low=94)) == "TP1"   # 再呼叫換 TP1


def test_update_price_moves_trigger():
    s = PaperFillSimulator()
    s.register("SL", "BTC", 90.0, LOW, 0)
    s.update_price("SL", 100.0)                            # 移至開倉價
    assert s.check("BTC", c(high=110, low=99)) == "SL"     # low<=100 成交


def test_symbol_isolation():
    s = PaperFillSimulator()
    s.register("E1", "BTC", 100.0, HIGH, 1)
    assert s.check("ETH", c(high=200, low=50)) is None     # 不同 symbol 不觸發
    assert s.check("BTC", c(high=101, low=99)) == "E1"


def test_unregister_removes_order():
    s = PaperFillSimulator()
    s.register("E1", "BTC", 100.0, HIGH, 1)
    s.unregister("E1")
    assert s.check("BTC", c(high=200, low=1)) is None
