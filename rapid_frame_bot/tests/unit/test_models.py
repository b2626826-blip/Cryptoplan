from models import Candle, FiboLevels, PatternContext, PositionContext


def test_candle_defaults_closed_true():
    c = Candle(open_time=1, open=10.0, high=12.0, low=9.0, close=11.0, volume=100.0)
    assert c.closed is True
    assert c.high == 12.0


def test_fibolevels_holds_all_levels():
    f = FiboLevels(fib_low=1.0, fib_high=2.0, sl=4.8, entry=6.8,
                   tp1=12.8, tp2=16.8, tp3=26.8)
    assert f.entry == 6.8


def test_position_context_defaults():
    p = PositionContext(symbol="BTCUSDT", timeframe="1h", position_id="1",
                        entry_price=100.0, total_qty=0.2, tpsl_id=None,
                        tp_order_ids=[])
    assert p.tp1_hit is False
    assert p.tp_order_ids == []
