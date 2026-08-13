# -*- coding: utf-8 -*-
"""缓存键与任务状态单元测试(纯函数,不触网)。"""

import asyncio

import main
from core.job_manager import MAX_PENDING_LOGS, JobStatus


# ---------- build_cache_key: 相同内容 + 不同检测选项 = 不同缓存 ----------

def test_same_content_diff_risk_threshold_diff_key():
    content = b"proxies: []"
    o1 = {"source": "ipapi", "fallback": True, "skip_keywords": ["官网"], "filter_risk_threshold": 30}
    o2 = {"source": "ipapi", "fallback": True, "skip_keywords": ["官网"], "filter_risk_threshold": 0}
    assert main.build_cache_key(content, o1) != main.build_cache_key(content, o2)


def test_same_content_diff_skip_keywords_diff_key():
    content = b"proxies: []"
    o1 = {"source": "ipapi", "skip_keywords": ["官网"], "filter_risk_threshold": 0}
    o2 = {"source": "ipapi", "skip_keywords": ["剩余"], "filter_risk_threshold": 0}
    assert main.build_cache_key(content, o1) != main.build_cache_key(content, o2)


def test_same_settings_same_key():
    content = b"proxies: []"
    o = {"source": "ipapi", "fallback": True, "skip_keywords": ["官网"], "filter_risk_threshold": 30}
    assert main.build_cache_key(content, o) == main.build_cache_key(content, dict(o))


def test_different_content_diff_key():
    assert main.build_cache_key(b"abc", {}) != main.build_cache_key(b"abd", {})


# ---------- JobStatus: 日志有上限,防止无人订阅 SSE 时无限堆积 ----------

def test_pending_logs_capped():
    job = JobStatus("url", "rid")

    async def run():
        for i in range(MAX_PENDING_LOGS + 50):
            await job.update_progress(0, 0, f"msg {i}")
        logs = await job.get_and_clear_logs()
        return logs

    logs = asyncio.run(run())
    assert len(logs) == MAX_PENDING_LOGS
    # 保留的是最新的 MAX_PENDING_LOGS 条
    assert logs[0] == f"msg {50}"
    assert logs[-1] == f"msg {MAX_PENDING_LOGS + 49}"
