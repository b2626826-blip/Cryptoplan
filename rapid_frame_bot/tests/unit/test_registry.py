import pytest
from exchanges.registry import build_adapter, SUPPORTED


def test_supported_contains_bitunix_and_bingx():
    assert "bitunix" in SUPPORTED
    assert "bingx" in SUPPORTED


def test_unknown_exchange_raises():
    with pytest.raises(ValueError):
        build_adapter("nonexistent", None, None)
