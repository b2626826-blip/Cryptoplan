import hashlib
import json

import pytest

from exchanges.bitunix.ws import (
    parse_kline_message,
    parse_order_message,
    CHANNEL_MAP,
    KlineCloseDetector,
    INTERVAL_MS,
    BitunixWS,
)
from models import Candle

H = 3600000  # 1h in ms


def _kline_msg(ts, o, h, l, c, b, ch="market_kline_60min", symbol="BTCUSDT"):
    """真實 Bitunix 格式：頂層 ts、data 內 o/h/l/c/b/q，無 t、無 closed。"""
    return {
        "ch": ch, "symbol": symbol, "ts": ts,
        "data": {"o": str(o), "c": str(c), "h": str(h), "l": str(l),
                 "b": str(b), "q": "0"},
    }


# ---------- parse_kline_message（真實格式）----------

def test_parse_kline_real_format():
    out = parse_kline_message(_kline_msg(1718000000000, 97000, 97500, 96800,
                                         97400, 150.5))
    assert out is not None
    symbol, ch, candle = out
    assert symbol == "BTCUSDT"
    assert ch == "market_kline_60min"
    assert candle.open == 97000.0
    assert candle.high == 97500.0
    assert candle.low == 96800.0
    assert candle.close == 97400.0
    assert candle.volume == 150.5         # 來自 data.b
    assert candle.open_time == 1718000000000  # 來自頂層 ts
    # 真實推送無收盤旗標 → 永遠 False（收盤由 KlineCloseDetector 判斷）
    assert candle.closed is False


def test_parse_kline_ignores_non_kline():
    assert parse_kline_message({"ch": "ping"}) is None
    assert parse_kline_message({"op": "subscribe"}) is None
    assert parse_kline_message({"op": "connect",
                                "data": {"result": True}}) is None


def test_parse_kline_requires_ts_and_symbol():
    # 缺 ts
    assert parse_kline_message(
        {"ch": "market_kline_60min", "symbol": "BTCUSDT",
         "data": {"o": "1", "h": "1", "l": "1", "c": "1", "b": "1"}}) is None
    # 缺 symbol
    assert parse_kline_message(
        {"ch": "market_kline_60min", "ts": 1,
         "data": {"o": "1", "h": "1", "l": "1", "c": "1", "b": "1"}}) is None


# ---------- parse_order_message ----------

def test_parse_order_filled():
    # 真實格式：狀態欄位為 orderStatus（非 status）
    msg = {"ch": "order", "ts": 1, "data": {
        "orderId": "OID9", "orderStatus": "FILLED", "event": "UPDATE"}}
    assert parse_order_message(msg) == ("OID9", "FILLED")


def test_parse_order_status_fallback():
    # 後備相容舊欄位名 status
    msg = {"ch": "order", "data": {"orderId": "OID1", "status": "NEW"}}
    assert parse_order_message(msg) == ("OID1", "NEW")


def test_parse_order_ignores_other():
    assert parse_order_message({"ch": "kline"}) is None
    # 缺 orderId 或狀態 → None
    assert parse_order_message({"ch": "order", "data": {"orderId": "X"}}) is None


# ---------- 私有 WS 登入簽名 ----------

def test_sign_login_formula():
    # 與 REST 不同：第一層只雜湊 nonce+timestamp+apiKey（無 query/body）
    nonce, ts, key, secret = "abc", "1700000000000", "API", "SECRET"
    digest = hashlib.sha256((nonce + ts + key).encode()).hexdigest()
    expected = hashlib.sha256((digest + secret).encode()).hexdigest()
    assert BitunixWS.sign_login(nonce, ts, key, secret) == expected


def test_build_login_shape():
    msg = BitunixWS.build_login("API", "SECRET")
    assert msg["op"] == "login"
    arg = msg["args"][0]
    assert arg["apiKey"] == "API"
    assert set(arg) == {"apiKey", "timestamp", "nonce", "sign"}
    # sign 與 sign_login 一致
    assert arg["sign"] == BitunixWS.sign_login(
        arg["nonce"], arg["timestamp"], "API", "SECRET")


# ---------- 私有連線分派 _dispatch_private ----------

class _FakeWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, raw):
        self.sent.append(json.loads(raw))


def _ws_with_capture():
    captured: list[tuple[str, str]] = []

    async def on_order(oid, status):
        captured.append((oid, status))

    ws = BitunixWS("pub", "priv", None, on_order,
                   api_key="API", api_secret="SECRET")
    return ws, captured


@pytest.mark.asyncio
async def test_private_connect_sends_login_then_subscribe():
    ws, _ = _ws_with_capture()
    fake = _FakeWS()
    await ws._dispatch_private(fake, {"op": "connect", "data": {"result": True}})
    assert len(fake.sent) == 2
    assert fake.sent[0]["op"] == "login"
    assert fake.sent[1] == {"op": "subscribe", "args": ["order"]}


@pytest.mark.asyncio
async def test_private_ping_replies_pong():
    ws, _ = _ws_with_capture()
    fake = _FakeWS()
    await ws._dispatch_private(fake, {"op": "ping", "ping": 12345})
    assert fake.sent == [{"op": "pong", "pong": 12345}]


@pytest.mark.asyncio
async def test_private_order_invokes_callback():
    ws, captured = _ws_with_capture()
    fake = _FakeWS()
    await ws._dispatch_private(
        fake, {"ch": "order", "data": {"orderId": "OID7", "orderStatus": "FILLED"}})
    assert captured == [("OID7", "FILLED")]
    assert fake.sent == []  # 訂單事件不回送任何訊息


# ---------- CHANNEL_MAP ----------

def test_channel_map():
    assert CHANNEL_MAP["1h"] == "market_kline_60min"
    assert CHANNEL_MAP["3h"] == "market_kline_60min"
    assert CHANNEL_MAP["1d"] == "market_kline_1day"
    assert CHANNEL_MAP["3d"] == "market_kline_3day"


def test_interval_ms_known_channels():
    assert INTERVAL_MS["market_kline_60min"] == 3600000
    assert INTERVAL_MS["market_kline_1day"] == 86400000
    assert INTERVAL_MS["market_kline_3day"] == 259200000


# ---------- KlineCloseDetector ----------

def _tick(ts, o, h, l, c, b=1.0):
    return Candle(open_time=ts, open=o, high=h, low=l, close=c,
                  volume=b, closed=False)


def test_detector_first_tick_returns_none():
    det = KlineCloseDetector()
    # 第一個 tick：尚無前一桶可收盤
    assert det.on_tick("BTCUSDT", "market_kline_60min",
                       _tick(0, 10, 11, 9, 10)) is None


def test_detector_same_bucket_returns_none():
    det = KlineCloseDetector()
    det.on_tick("BTCUSDT", "market_kline_60min", _tick(0, 10, 11, 9, 10))
    # 同一小時桶內再來一個 tick，尚未收盤
    assert det.on_tick("BTCUSDT", "market_kline_60min",
                       _tick(60000, 10, 12, 9, 11)) is None


def test_detector_bucket_rollover_emits_closed_candle():
    det = KlineCloseDetector()
    # 第 0 小時桶的兩個 tick（最後一個值為收盤值）
    det.on_tick("BTCUSDT", "market_kline_60min", _tick(0, 10, 11, 9, 10))
    det.on_tick("BTCUSDT", "market_kline_60min", _tick(H - 1000, 10, 15, 8, 13))
    # 跨入第 1 小時桶 → 收盤前一根
    closed = det.on_tick("BTCUSDT", "market_kline_60min",
                         _tick(H + 500, 13, 14, 12, 13))
    assert closed is not None
    assert closed.closed is True
    assert closed.open == 10           # 第 0 桶最後 tick 的 open
    assert closed.high == 15
    assert closed.low == 8
    assert closed.close == 13
    assert closed.open_time == 0       # 對齊到桶起點 0*interval


def test_detector_symbol_channel_isolation():
    det = KlineCloseDetector()
    det.on_tick("BTCUSDT", "market_kline_60min", _tick(0, 10, 11, 9, 10))
    det.on_tick("ETHUSDT", "market_kline_60min", _tick(0, 100, 110, 90, 100))
    # BTC 跨桶收盤，不影響 ETH
    closed = det.on_tick("BTCUSDT", "market_kline_60min",
                         _tick(H + 1, 10, 10, 10, 10))
    assert closed is not None and closed.open == 10
    assert det.on_tick("ETHUSDT", "market_kline_60min",
                       _tick(60000, 100, 120, 95, 110)) is None


def test_detector_unknown_channel_returns_none():
    det = KlineCloseDetector()
    assert det.on_tick("BTCUSDT", "no_such_channel",
                       _tick(0, 1, 1, 1, 1)) is None
