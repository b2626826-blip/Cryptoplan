from __future__ import annotations
from dataclasses import dataclass, field
import yaml
from config_secrets import load_keys


@dataclass
class ExchangeConfig:
    name: str
    enabled: bool
    symbols: list[str]
    major_leverage: int
    altcoin_leverage: int
    major_timeframes: list[str]
    altcoin_timeframes: list[str]
    max_concurrent_positions: int
    risk_per_trade: float
    qty_step: float
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = True  # fail-safe：未明確指定時預設紙上（不打真實單）；正常由全域 testnet 灌入，供 Executor.paper 使用


@dataclass
class Config:
    testnet: bool
    log_level: str
    log_file: str
    email_smtp_host: str
    email_smtp_port: int
    email_sender: str
    email_password: str
    email_recipient: str
    exchanges: dict[str, ExchangeConfig] = field(default_factory=dict)

    @property
    def enabled_exchanges(self) -> dict[str, ExchangeConfig]:
        return {n: c for n, c in self.exchanges.items() if c.enabled}


def load_config(path: str, secrets_dir: str = "secrets") -> Config:
    with open(path, "r", encoding="utf-8") as f:
        d = yaml.safe_load(f)
    e, lg = d["email"], d["logging"]
    testnet = bool(d.get("testnet", True))
    exchanges: dict[str, ExchangeConfig] = {}
    for name, x in (d.get("exchanges") or {}).items():
        api_key, api_secret = load_keys(name, secrets_dir=secrets_dir)
        exchanges[name] = ExchangeConfig(
            name=name, enabled=bool(x.get("enabled", False)),
            symbols=list(x["symbols"]),
            major_leverage=int(x["major_leverage"]),
            altcoin_leverage=int(x["altcoin_leverage"]),
            major_timeframes=list(x["major_timeframes"]),
            altcoin_timeframes=list(x["altcoin_timeframes"]),
            max_concurrent_positions=int(x["max_concurrent_positions"]),
            risk_per_trade=float(x["risk_per_trade"]),
            qty_step=float(x["qty_step"]),
            api_key=api_key, api_secret=api_secret, testnet=testnet)
    return Config(
        testnet=testnet,
        log_level=lg["level"], log_file=lg["file"],
        email_smtp_host=e["smtp_host"], email_smtp_port=int(e["smtp_port"]),
        email_sender=e["sender"], email_password=e["password"],
        email_recipient=e["recipient"], exchanges=exchanges)
