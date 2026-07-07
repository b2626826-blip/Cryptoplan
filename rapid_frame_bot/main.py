from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone

import aiohttp
from loguru import logger

from config import Config, load_config
from session import ExchangeSession
from exchanges.registry import build_adapter
from notify.email_notifier import EmailNotifier


class Coordinator:
    """並行運行多個 ExchangeSession（每家獨立倉位/本金/告警），含故障隔離。"""

    def __init__(self, config: Config) -> None:
        self.cfg = config
        self.notifier = EmailNotifier(config)
        self.sessions: list[ExchangeSession] = []

    async def run_session_guarded(self, session: ExchangeSession) -> None:
        """單一 session 的例外隔離：記錄 + 發告警，不向外拋（不拖垮其他家）。"""
        try:
            await session.run()
        except Exception as exc:  # noqa: BLE001
            name = getattr(session.ex, "name", "?")
            logger.error(f"[{name}] session 異常終止：{exc}")
            await self.notifier.send(
                f"[{name}] 交易所 session 異常終止", str(exc))

    async def daily_signal_check(self) -> None:  # pragma: no cover
        while True:
            now = datetime.now(timezone.utc)
            target = now.replace(hour=23, minute=55, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            await asyncio.sleep((target - now).total_seconds())
            total = sum(s.shared.daily_signal_count for s in self.sessions)
            if total == 0:
                await self.notifier.send(
                    "今日無符合條件型態",
                    "所有交易所本交易日皆未偵測到符合條件的進場訊號。")
            for s in self.sessions:
                s.shared.reset_daily()

    async def run(self) -> None:  # pragma: no cover - 整合啟動
        async with aiohttp.ClientSession() as http:
            for name, ex_cfg in self.cfg.enabled_exchanges.items():
                adapter = build_adapter(name, ex_cfg, http)
                self.sessions.append(
                    ExchangeSession(adapter, ex_cfg, self.notifier,
                                    testnet=self.cfg.testnet))
            logger.info(f"啟用交易所：{[s.ex.name for s in self.sessions]}")
            await asyncio.gather(
                *(self.run_session_guarded(s) for s in self.sessions),
                self.daily_signal_check())


def main() -> None:  # pragma: no cover
    cfg = load_config("config.yaml")
    logger.add(cfg.log_file, level=cfg.log_level)
    asyncio.run(Coordinator(cfg).run())


if __name__ == "__main__":  # pragma: no cover
    main()
