from __future__ import annotations
import asyncio
from loguru import logger

from config import ExchangeConfig
from exchanges.base import Exchange
from models import Candle, OrderEvent, PositionContext
from shared_state import SharedState
from strategy.candle_builder import CandleBuilder3H
from strategy.state_machine import StateMachine, IN_POSITION
from trader.executor import Executor
from trader.paper_sim import PaperFillSimulator
from exchanges.bitunix.ws import CHANNEL_MAP

CAPITAL_REFRESH_INTERVAL = 300


class ExchangeSession:
    """單一交易所的完整執行環境：獨立 capital/state/串流/恢復/路由。"""

    def __init__(self, exchange: Exchange, ex_cfg: ExchangeConfig,
                 notifier, testnet: bool) -> None:
        self.ex = exchange
        self.cfg = ex_cfg
        self.notifier = notifier
        self.testnet = testnet
        self.shared = SharedState(ex_cfg.max_concurrent_positions)
        self.capital = 0.0
        self.paper_sim = PaperFillSimulator() if testnet else None
        self.executor = Executor(exchange, ex_cfg, notifier,
                                 paper_sim=self.paper_sim)
        self.symbols = list(ex_cfg.symbols)
        self.state_machines: dict[tuple[str, str], StateMachine] = {}
        self.builders: dict[str, CandleBuilder3H] = {}

    def _leverage_for(self, symbol: str) -> int:
        return self.cfg.major_leverage  # 單一 symbols 清單，沿用 major 槓桿

    def _timeframes_for(self, symbol: str) -> list[str]:
        return self.cfg.major_timeframes

    def build_state_machines(self) -> dict[tuple[str, str], StateMachine]:
        sms: dict[tuple[str, str], StateMachine] = {}
        for symbol in self.symbols:
            self.builders.setdefault(symbol, CandleBuilder3H())
            for tf in self._timeframes_for(symbol):
                sms[(symbol, tf)] = StateMachine(
                    symbol, tf, self.executor, self.shared, self.cfg,
                    qty_step=self.ex.qty_step, leverage=self._leverage_for(symbol))
        return sms

    def build_subscriptions(self) -> list[tuple[str, str]]:
        subs: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for symbol in self.symbols:
            for tf in self._timeframes_for(symbol):
                pair = (symbol, CHANNEL_MAP[tf])
                if pair not in seen:
                    seen.add(pair)
                    subs.append(pair)
        return subs

    async def refresh_capital(self) -> None:
        self.capital = await self.ex.get_available_capital()
        if self.capital <= 0:
            logger.warning(f"[{self.ex.name}] 可用資金為 0，暫停開倉")
            await self.notifier.send(
                f"[{self.ex.name}] 帳戶資金不足", "可用資金為 0，暫停開倉。")

    async def capital_refresh_loop(self) -> None:  # pragma: no cover
        while True:
            await asyncio.sleep(CAPITAL_REFRESH_INTERVAL)
            try:
                await self.refresh_capital()
            except Exception as exc:  # noqa: BLE001
                logger.error(f"[{self.ex.name}] 刷新資金失敗：{exc}")

    async def route_candle(self, symbol: str, channel: str,
                           candle: Candle) -> None:
        if channel == CHANNEL_MAP["1h"]:
            sm = self.state_machines.get((symbol, "1h"))
            if sm:
                await sm.on_candle_close(candle, self.capital)
            builder = self.builders.setdefault(symbol, CandleBuilder3H())
            synth = builder.on_1h_close(symbol, candle)
            if synth:
                sm3 = self.state_machines.get((symbol, "3h"))
                if sm3:
                    await sm3.on_candle_close(synth, self.capital)
        elif channel == CHANNEL_MAP["1d"]:
            sm = self.state_machines.get((symbol, "1d"))
            if sm:
                await sm.on_candle_close(candle, self.capital)
        elif channel == CHANNEL_MAP["3d"]:
            sm = self.state_machines.get((symbol, "3d"))
            if sm:
                await sm.on_candle_close(candle, self.capital)
        if self.paper_sim is not None:
            for _ in range(20):
                oid = self.paper_sim.check(symbol, candle)
                if oid is None:
                    break
                await self.route_order(OrderEvent(oid, "FILLED", {}))

    async def route_order(self, event: OrderEvent) -> None:
        if event.status != "FILLED":
            return
        for sm in self.state_machines.values():
            await sm.on_order_filled(event.order_id)

    async def recover_positions(self) -> None:
        if not self.state_machines:
            self.state_machines = self.build_state_machines()
        for pos in await self.ex.fetch_positions():
            self.shared.mark_open(pos.symbol)
            sm = self._primary_sm(pos.symbol)
            if sm is None:
                logger.warning(f"[{self.ex.name}] 恢復 {pos.symbol}：無狀態機，僅標記")
                continue
            orders = await self.ex.fetch_open_orders(pos.symbol)
            tp_ids, sl_id = _classify_orders(orders)
            sm.position = PositionContext(
                symbol=pos.symbol, timeframe=sm.timeframe,
                position_id=pos.position_id, entry_price=pos.entry_price,
                total_qty=pos.qty, tpsl_id=sl_id, tp_order_ids=tp_ids, fibo=None)
            sm.state = IN_POSITION
            logger.info(
                f"[{self.ex.name}] 恢復持倉 {pos.symbol} @ {pos.entry_price} "
                f"qty={pos.qty} tp={len(tp_ids)} sl={'有' if sl_id else '無'}")

    def _primary_sm(self, symbol: str) -> StateMachine | None:
        for tf in self._timeframes_for(symbol):
            sm = self.state_machines.get((symbol, tf))
            if sm is not None:
                return sm
        return None

    async def run(self) -> None:  # pragma: no cover - 整合啟動
        await self.refresh_capital()
        self.state_machines = self.build_state_machines()
        for symbol in self.symbols:
            await self.executor.setup_symbol(symbol, self._leverage_for(symbol))
        await self.recover_positions()
        subs = self.build_subscriptions()
        if self.ex.supports_combined_stream():
            await asyncio.gather(
                self.ex.run_streams(subs, self.route_candle, self.route_order),
                self.capital_refresh_loop())
        else:
            await asyncio.gather(
                self.ex.stream_candles(subs, self.route_candle),
                self.ex.stream_orders(self.route_order),
                self.capital_refresh_loop())


def _classify_orders(orders: list[dict]) -> tuple[list[str], str | None]:
    """從 main.py 搬來的掛單分類（reduce-only SELL LIMIT = TP；含 STOP = SL）。"""
    tps: list[tuple[float, str]] = []
    sl_id: str | None = None
    for o in orders:
        oid = str(o.get("orderId") or o.get("orderID") or "")
        if not oid:
            continue
        otype = str(o.get("orderType") or "").upper()
        side = str(o.get("side") or "").upper()
        reduce_only = bool(o.get("reduceOnly"))
        if otype == "LIMIT" and side == "SELL" and reduce_only:
            tps.append((float(o.get("price") or 0), oid))
        elif "STOP" in otype or o.get("slPrice") is not None:
            sl_id = oid
    tps.sort(key=lambda t: t[0])
    return [oid for _, oid in tps], sl_id
