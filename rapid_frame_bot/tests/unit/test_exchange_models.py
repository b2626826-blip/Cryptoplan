from models import OrderResult, OrderEvent, Position
from exchanges.base import Exchange, ExchangeError


def test_order_result_holds_id_and_raw():
    r = OrderResult(order_id="abc", raw={"data": {"orderId": "abc"}})
    assert r.order_id == "abc"
    assert r.raw["data"]["orderId"] == "abc"


def test_order_event_normalized_status():
    e = OrderEvent(order_id="1", status="FILLED", raw={"orderStatus": "FILLED"})
    assert e.status == "FILLED"


def test_position_fields():
    p = Position(symbol="BTCUSDT", position_id="p1", entry_price=100.0,
                 qty=0.5, raw={})
    assert p.symbol == "BTCUSDT" and p.qty == 0.5


def test_exchange_is_abstract():
    import pytest
    with pytest.raises(TypeError):
        Exchange()  # 抽象類別不可實例化


def test_exchange_error_is_exception():
    assert issubclass(ExchangeError, Exception)
