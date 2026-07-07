"""Coordinator 測試：多 session 並行與故障隔離。
（個別 session 的路由/恢復行為見 test_session.py / test_live_readiness.py。）"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from main import Coordinator


@pytest.mark.asyncio
async def test_one_session_failure_does_not_stop_others():
    cfg = MagicMock()
    coord = Coordinator(cfg)
    coord.notifier = AsyncMock()
    good = AsyncMock()
    bad = AsyncMock()
    bad.run.side_effect = RuntimeError("boom")
    bad.ex = MagicMock()
    bad.ex.name = "bad"
    # run_session_guarded 應吞掉例外、發告警，不向外拋
    await coord.run_session_guarded(bad)
    await coord.run_session_guarded(good)
    good.run.assert_awaited_once()
    coord.notifier.send.assert_awaited()  # 對 bad 發了告警
