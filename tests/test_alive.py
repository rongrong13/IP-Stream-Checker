# -*- coding: utf-8 -*-
"""测活并发控制单元测试(模拟 Mihomo API,不触网)。"""

import asyncio

from core.clash_api import ClashController


def test_alive_batch_respects_concurrency():
    """信号量应把并发限制在配置值内(通过模拟记录最大同时请求数)。"""
    peak = {"v": 0}
    current = {"v": 0}
    lock = asyncio.Lock()

    async def fake_delay(self_, name, url, timeout_ms):
        async with lock:
            current["v"] += 1
            peak["v"] = max(peak["v"], current["v"])
        await asyncio.sleep(0.02)  # 模拟一次测活
        async with lock:
            current["v"] -= 1
        return 123  # 全部存活

    # 用 monkeypatch 替换实例方法
    c = ClashController("http://x")
    c.test_proxy_delay = fake_delay.__get__(c, ClashController)

    names = [f"node-{i}" for i in range(20)]
    async def run():
        return await c.test_alive_batch(names, concurrency=5)

    result = asyncio.run(run())
    assert peak["v"] <= 5
    assert len(result) == 20


def test_alive_batch_empty():
    c = ClashController("http://x")
    assert asyncio.run(c.test_alive_batch([], concurrency=5)) == {}


def test_alive_batch_concurrency_clamped():
    """并发数超过节点数时自动收敛到节点数。"""
    peak = {"v": 0}
    current = {"v": 0}
    lock = asyncio.Lock()

    async def fake_delay(self_, name, url, timeout_ms):
        async with lock:
            current["v"] += 1
            peak["v"] = max(peak["v"], current["v"])
        await asyncio.sleep(0.01)
        async with lock:
            current["v"] -= 1
        return 1

    c = ClashController("http://x")
    c.test_proxy_delay = fake_delay.__get__(c, ClashController)

    async def run():
        return await c.test_alive_batch(["a", "b"], concurrency=50)

    result = asyncio.run(run())
    assert peak["v"] <= 2
    assert len(result) == 2
