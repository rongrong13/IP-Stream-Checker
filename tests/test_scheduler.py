# -*- coding: utf-8 -*-
"""定时调度器单元测试(把心跳调小模拟,不触网)。"""

import asyncio
import time

import core.scheduler as scheduler_mod
from core.scheduler import Scheduler

# 把心跳调小,让测试快速跑多个周期
scheduler_mod.TICK_SECONDS = 0.05


def test_parse_cron_valid():
    s = Scheduler()
    assert s._parse_cron("0 3 * * *") is not None
    assert s._parse_cron("*/30 * * * *") is not None
    assert s._parse_cron("1-10/2 * * * *") is not None


def test_parse_cron_invalid():
    s = Scheduler()
    assert s._parse_cron("not a cron") is None
    assert s._parse_cron("") is None


def test_compute_delay_interval():
    s = Scheduler()
    s._last_interval_run = time.time() - 100  # 距上次触发已过 100s
    d = s._compute_delay({"cron": "", "interval_minutes": 60})
    assert d is not None and 0 <= d <= 60 * 60


def test_compute_delay_none():
    s = Scheduler()
    assert s._compute_delay({"cron": "bad expr", "interval_minutes": 0}) is None


def test_interval_fires_once_per_window():
    """间隔触发: 同一时间窗口内只触发一次(与 subs-check check-interval 语义一致)。"""
    calls = []
    s = Scheduler()
    s.on_trigger = lambda url: calls.append(url)
    s._last_interval_run = 0.0  # 模拟从未触发过

    async def get_schedule():
        return {"enabled": True, "cron": "", "interval_minutes": 1,
                "urls": ["https://example.com/sub"]}

    async def run():
        task = asyncio.create_task(s._loop(get_schedule))
        await asyncio.sleep(0.25)  # 跑 ~5 个心跳周期
        await s.stop()

    asyncio.run(run())
    assert calls.count("https://example.com/sub") == 1


def test_disabled_no_fire():
    """schedule.enabled=false 时不触发。"""
    calls = []
    s = Scheduler()
    s.on_trigger = lambda url: calls.append(url)
    s._last_interval_run = 0.0

    async def get_schedule():
        return {"enabled": False, "cron": "", "interval_minutes": 1,
                "urls": ["https://example.com/sub"]}

    async def run():
        task = asyncio.create_task(s._loop(get_schedule))
        await asyncio.sleep(0.15)
        await s.stop()

    asyncio.run(run())
    assert calls == []
