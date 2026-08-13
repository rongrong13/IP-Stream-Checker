# -*- coding: utf-8 -*-
"""定时自动检测调度器(参考 subs-check 的 cron-expression / check-interval)。

两种触发方式(可同时配置,以先到者为准):
- cron 表达式(5 段: 分 时 日 月 周), 如 "0 3 * * *" = 每天 03:00
- 间隔分钟, 如 60 = 每 60 分钟

到点后对 schedule.urls 中的每个订阅 URL 触发一次检测(复用 /check 的完整流程,
结果写入历史记录,可在 Web 面板回看)。同一 URL 已有活跃任务时跳过,避免堆积。
"""

import asyncio
import logging
import time
from typing import List, Optional

logger = logging.getLogger("Scheduler")

# 调度器心跳间隔(秒): 每 15 秒检查一次是否到点
TICK_SECONDS = 15


class Scheduler:
    def __init__(self, on_trigger=None):
        """on_trigger: 异步回调(url: str) -> None,在到点时被调用。"""
        self.on_trigger = on_trigger
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._last_interval_run = 0.0
        self._last_cron_run = ""

    def _parse_cron(self, expr: str):
        """把 5 段 cron 表达式解析为 [(分钟集合|None, 小时集合|None, ...)] 形式。

        返回 None 表示解析失败(调用方应记录并回退到间隔模式)。
        支持: * 任意、具体数字、列表(1,2,3)、范围(1-5)、步进(*/5、1-10/2)。
        """
        try:
            import croniter  # 运行时才导入,避免未启用定时检测时额外依赖
            croniter.croniter(expr, time.time())  # 校验表达式是否合法
            return expr
        except Exception:
            return None

    def _compute_delay(self, schedule: dict) -> Optional[float]:
        """计算距离下次触发还有多少秒;无可用触发方式返回 None。"""
        cron_expr = (schedule.get("cron") or "").strip()
        interval = int(schedule.get("interval_minutes", 0) or 0)
        now = time.time()

        candidates = []
        if cron_expr and self._parse_cron(cron_expr):
            import croniter
            it = croniter.croniter(cron_expr, now)
            candidates.append(it.get_next(float) - now)
        if interval > 0:
            elapsed = now - self._last_interval_run
            candidates.append(max(0.0, interval * 60 - elapsed))

        return min(candidates) if candidates else None

    def _cron_fired(self, cron_expr: str) -> bool:
        """判断当前是否处于 cron 表达式定义的分钟窗口(用分钟粒度对齐,避免秒级抖动)。"""
        import croniter
        now = time.localtime()
        this_min = time.strftime("%Y-%m-%d %H:%M", now)
        it = croniter.croniter(cron_expr, now)
        # 下一次触发(取整分钟对齐)
        nxt = time.localtime(int(it.get_next(float)))
        nxt_min = time.strftime("%Y-%m-%d %H:%M", nxt)
        return this_min == nxt_min

    async def _loop(self, get_schedule):
        """主循环: 每 TICK_SECONDS 检查一次,到点触发。get_schedule 为无参回调返回配置 dict。"""
        while True:
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=TICK_SECONDS)
                return  # 收到停止信号
            except asyncio.TimeoutError:
                pass

            schedule = get_schedule()
            if asyncio.iscoroutine(schedule):
                schedule = await schedule
            if not schedule or not schedule.get("enabled"):
                continue

            now = time.time()
            interval = int(schedule.get("interval_minutes", 0) or 0)
            cron_expr = (schedule.get("cron") or "").strip()
            urls = schedule.get("urls") or []

            if interval > 0:
                if now - self._last_interval_run >= interval * 60:
                    self._last_interval_run = now
                    await self._fire(urls, "interval")
                    continue  # 同一轮只触发一次
            if cron_expr and self._parse_cron(cron_expr):
                # cron 按分钟窗口触发,记录上次触发的分钟串防止重复触发
                key = time.strftime("%Y-%m-%d %H:%M")
                if self._cron_fired(cron_expr) and key != self._last_cron_run:
                    self._last_cron_run = key
                    await self._fire(urls, "cron")

    async def _fire(self, urls: List[str], mode: str):
        """对每个订阅 URL 触发一次检测(带日志与异常兜底)。"""
        print(f"[SCHEDULE] 定时触发({mode}) 检测 {len(urls)} 个订阅", flush=True)
        if not self.on_trigger or not urls:
            return
        for url in urls:
            try:
                await self.on_trigger(url)
            except Exception as e:
                print(f"[SCHEDULE] 触发检测失败 {url}: {e}", flush=True)

    def start(self, get_schedule):
        """启动调度器(幂等)。get_schedule: 无参回调,返回当前 schedule 配置 dict。"""
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(get_schedule))
        print("[SCHEDULE] 定时检测调度器已启动(心跳每 15 秒)", flush=True)

    async def stop(self):
        """停止调度器。"""
        if self._task and not self._task.done():
            self._stop.set()
            try:
                await asyncio.wait_for(self._task, timeout=TICK_SECONDS + 2)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        self._task = None
        print("[SCHEDULE] 定时检测调度器已停止", flush=True)
