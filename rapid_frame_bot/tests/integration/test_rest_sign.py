import hashlib
from exchanges.bitunix.rest import BitunixREST


def test_sign_double_sha256():
    nonce, ts, key, secret = "abc", "1700000000000", "API", "SECRET"
    query, body = "symbol=BTCUSDT", '{"a":1}'
    digest = hashlib.sha256(
        (nonce + ts + key + query + body).encode()
    ).hexdigest()
    expected = hashlib.sha256((digest + secret).encode()).hexdigest()
    assert BitunixREST.sign(nonce, ts, key, query, body, secret) == expected


def test_build_query_ascii_sorted():
    # Bitunix 規格：keys 依 ASCII 升序，串接為 key+value（無 = 與 &）
    q = BitunixREST._build_query({"symbol": "BTCUSDT", "limit": "50",
                                  "interval": "1h"})
    assert q == "interval1hlimit50symbolBTCUSDT"


def test_build_query_empty():
    assert BitunixREST._build_query({}) == ""
