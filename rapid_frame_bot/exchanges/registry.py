from __future__ import annotations

SUPPORTED = {"bitunix", "bingx", "binance", "bybit", "okx"}


def build_adapter(name: str, ex_cfg, session):
    """依交易所名字建立對應 adapter。session 提供 aiohttp session 等共用資源。"""
    name = name.lower()
    if name == "bitunix":
        from exchanges.bitunix.rest import BitunixREST
        from exchanges.bitunix.ws import BitunixWS
        from exchanges.bitunix.adapter import BitunixAdapter
        rest = BitunixREST(ex_cfg, session)

        def ws_factory(on_candle, on_order):
            return BitunixWS(
                "wss://fapi.bitunix.com/public/",
                "wss://fapi.bitunix.com/private/",
                on_candle, on_order,
                api_key=ex_cfg.api_key, api_secret=ex_cfg.api_secret)

        return BitunixAdapter(rest=rest, ws_factory=ws_factory,
                              qty_step=ex_cfg.qty_step)
    if name in {"bingx", "binance", "bybit", "okx"}:
        from exchanges.ccxt_based.adapter import CcxtAdapter
        return CcxtAdapter(exchange_id=name, ex_cfg=ex_cfg)
    raise ValueError(f"未支援的交易所：{name}（支援：{sorted(SUPPORTED)}）")
