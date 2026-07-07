import textwrap
from config import load_config, ExchangeConfig
from shared_state import SharedState


def test_exchange_config_testnet_defaults_to_paper():
    # fail-safe：省略 testnet 時應預設 True（紙上），絕不可靜默變成實盤
    cfg = ExchangeConfig(
        name="bitunix", enabled=True, symbols=["BTCUSDT"],
        major_leverage=10, altcoin_leverage=5,
        major_timeframes=["1h"], altcoin_timeframes=["1d"],
        max_concurrent_positions=3, risk_per_trade=0.02, qty_step=0.001)
    assert cfg.testnet is True


def test_load_multi_exchange(tmp_path, monkeypatch):
    monkeypatch.setenv("BITUNIX_API_KEY", "k")
    monkeypatch.setenv("BITUNIX_API_SECRET", "s")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(textwrap.dedent("""
        testnet: true
        logging: { level: INFO, file: bot.log }
        email: { smtp_host: h, smtp_port: 465, sender: a, password: p, recipient: r }
        exchanges:
          bitunix:
            enabled: true
            symbols: [BTCUSDT]
            major_leverage: 10
            altcoin_leverage: 5
            major_timeframes: [1h, 3h]
            altcoin_timeframes: [1d]
            max_concurrent_positions: 3
            risk_per_trade: 0.02
            qty_step: 0.001
          bingx:
            enabled: false
            symbols: [BTC-USDT]
            major_leverage: 10
            altcoin_leverage: 5
            major_timeframes: [1h]
            altcoin_timeframes: [1d]
            max_concurrent_positions: 2
            risk_per_trade: 0.02
            qty_step: 0.0001
    """), encoding="utf-8")
    cfg = load_config(str(cfg_file), secrets_dir=str(tmp_path))
    assert cfg.testnet is True
    assert set(cfg.exchanges) == {"bitunix", "bingx"}
    assert set(cfg.enabled_exchanges) == {"bitunix"}      # 只有 enabled 的
    assert cfg.exchanges["bitunix"].api_key == "k"
    assert cfg.exchanges["bitunix"].qty_step == 0.001
    # 全域 testnet 灌入各 ExchangeConfig（供 Executor.paper 使用）
    assert cfg.exchanges["bitunix"].testnet is True


def test_shared_state_capacity():
    s = SharedState(max_positions=2)
    assert s.can_open() is True
    s.mark_open("BTCUSDT")
    s.mark_open("ETHUSDT")
    assert s.active_position_count() == 2
    assert s.can_open() is False
    s.mark_closed("BTCUSDT")
    assert s.can_open() is True


def test_shared_state_signal_counter():
    s = SharedState(max_positions=7)
    assert s.daily_signal_count == 0
    s.record_signal()
    s.record_signal()
    assert s.daily_signal_count == 2
    s.reset_daily()
    assert s.daily_signal_count == 0


def test_mark_open_idempotent_count():
    s = SharedState(max_positions=7)
    s.mark_open("BTCUSDT")
    s.mark_open("BTCUSDT")
    assert s.active_position_count() == 1
