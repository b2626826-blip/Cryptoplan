from __future__ import annotations
import time

from loguru import logger
from exchanges.base import Exchange
from models import FiboLevels
from trader.paper_sim import PaperFillSimulator, HIGH, LOW

TP_RATIOS = (0.30, 0.30, 0.28)


class Executor:
    def __init__(self, exchange: Exchange, config,
                 notifier,
                 paper_sim: "PaperFillSimulator | None" = None) -> None:
        self.ex = exchange
        self.cfg = config
        self.notifier = notifier
        self.paper_sim = paper_sim

    @property
    def paper(self) -> bool:
        return self.cfg.testnet

    async def setup_symbol(self, symbol: str, leverage: int) -> None:
        if self.paper:
            logger.info(f"[PAPER] setup {symbol} lev={leverage} cross")
            return
        await self.ex.setup_symbol(symbol, leverage)

    async def place_entry(self, symbol: str, qty: float, entry_price: float,
                          client_id: str) -> str | None:
        if self.paper:
            pid = f"paper_{symbol}_{int(time.time()*1000)}"
            logger.info(f"[PAPER] entry {symbol} qty={qty} @ {entry_price} -> {pid}")
            if self.paper_sim is not None:
                self.paper_sim.register(pid, symbol, entry_price, HIGH, 1)
            return pid
        result = await self.ex.place_entry(symbol, qty, entry_price, client_id)
        return result.order_id

    async def cancel_entry(self, symbol: str, order_id: str) -> None:
        if self.paper:
            logger.info(f"[PAPER] cancel entry {symbol} {order_id}")
            if self.paper_sim is not None:
                self.paper_sim.unregister(order_id)
            return
        await self.ex.cancel(symbol, [order_id])

    async def on_entry_filled(self, symbol: str, position_id: str, qty: float,
                              entry_price: float, fibo: FiboLevels) -> dict:
        tpsl_id = await self._place_sl(symbol, position_id, fibo.sl)
        tp_ids: list[str] = []
        for ratio, price, tag, prio in zip(
            TP_RATIOS, (fibo.tp1, fibo.tp2, fibo.tp3),
            ("tp1", "tp2", "tp3"), (2, 3, 4)
        ):
            oid = await self._place_tp(symbol, qty * ratio, price,
                                       f"{tag}_{symbol}_{int(time.time())}", prio)
            tp_ids.append(oid)
        await self.notifier.send(
            "進場成交",
            f"{symbol} 進場 @ {entry_price} qty={qty}\n"
            f"SL={fibo.sl} TP1={fibo.tp1} TP2={fibo.tp2} TP3={fibo.tp3}")
        return {"tpsl_id": tpsl_id, "tp_order_ids": tp_ids}

    async def _place_sl(self, symbol: str, position_id: str, sl_price: float) -> str | None:
        if self.paper:
            logger.info(f"[PAPER] SL {symbol} @ {sl_price}")
            sl_id = f"paper_sl_{symbol}"
            if self.paper_sim is not None:
                self.paper_sim.register(sl_id, symbol, sl_price, LOW, 0)
            return sl_id
        result = await self.ex.place_sl(symbol, position_id, sl_price)
        return result.order_id

    async def _place_tp(self, symbol: str, qty: float, price: float,
                        client_id: str, priority: int = 2) -> str | None:
        if self.paper:
            pid = f"paper_{client_id}"
            logger.info(f"[PAPER] TP {symbol} qty={qty} @ {price}")
            if self.paper_sim is not None:
                self.paper_sim.register(pid, symbol, price, HIGH, priority)
            return pid
        result = await self.ex.place_tp(symbol, qty, price, client_id)
        return result.order_id

    async def move_sl_to_entry(self, symbol: str, tpsl_id: str,
                               entry_price: float) -> None:
        if self.paper:
            logger.info(f"[PAPER] move SL {symbol} -> {entry_price}")
            if self.paper_sim is not None:
                self.paper_sim.update_price(tpsl_id, entry_price)
            return
        await self.ex.move_sl(symbol, tpsl_id, entry_price)

    async def cancel_tp_orders(self, symbol: str, order_ids: list[str]) -> None:
        if self.paper:
            logger.info(f"[PAPER] cancel TPs {symbol} {order_ids}")
            if self.paper_sim is not None:
                for oid in order_ids:
                    self.paper_sim.unregister(oid)
            return
        await self.ex.cancel(symbol, order_ids)

    async def close_remaining(self, symbol: str, position_id: str,
                              remaining_qty: float, tpsl_id: str | None) -> None:
        if self.paper:
            logger.info(f"[PAPER] close remaining {symbol} qty={remaining_qty}")
            if tpsl_id:
                logger.info(f"[PAPER] cancel breakeven SL {symbol} {tpsl_id}")
            if self.paper_sim is not None and tpsl_id:
                self.paper_sim.unregister(tpsl_id)
        else:
            await self.ex.close_market(symbol, remaining_qty)
            if tpsl_id:
                await self.ex.cancel(symbol, [tpsl_id])
        await self.notifier.send(
            "剩餘部位平倉",
            f"{symbol} 市價全平剩餘 {remaining_qty}")
