# -*- coding: utf-8 -*-
"""流媒体解锁检测集成层

通过 subprocess 调用 MediaUnlockTest 二进制(Go 编写,位于 mediatest/),
对其 -json 模式输出的结构化结果进行解析,并提供节点名标注用的短摘要。

调用示例(Go 侧,由 runJSONMode 实现):
    mediatest -json -http-proxy http://127.0.0.1:7890 -conc 20 \\
              -providers "Netflix,Disney+,OpenAI ChatGPT"
输出(JSON 数组):
    [{"name": "Netflix", "status": 1, "status_text": "ok",
      "region": "US", "info": "", "ok": true}, ...]

status_text 取值: ok / restricted / no / network_error / error / banned / failed / unexpected
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("MediaUnlockTester")

# 服务名 → 节点名标注用的短缩写(未映射的服务使用原名前几个字符)
PROVIDER_ABBR: Dict[str, str] = {
    "Netflix": "NF",
    "Netflix CDN": "NF-CDN",
    "Disney+": "D+",
    "Youtube Premium": "YT",
    "Youtube CDN": "YT-CDN",
    "OpenAI ChatGPT": "GPT",
    "Anthropic Claude": "Claude",
    "Google Gemini": "GM",
    "Microsoft Copilot": "Copilot",
    "Spotify Registration": "Spotify",
    "Amazon Prime Video": "Prime",
    "Hulu": "Hulu",
    "HBO Max": "Max",
    "TikTok": "TikTok",
    "Steam": "Steam",
    "Reddit": "Reddit",
    "Apple": "Apple",
    "Bing": "Bing",
    "Dazn": "Dazn",
}


class MediaUnlockTester:
    """封装 MediaUnlockTest 二进制的调用与结果解析。"""

    def __init__(
        self,
        binary_path: str = "/usr/local/bin/mediatest",
        providers: Optional[List[str]] = None,
        timeout: int = 90,
        conc: int = 20,
    ):
        # MediaUnlockTest 二进制路径
        self.binary_path = binary_path
        # 要测试的服务名列表(空 = 全部,耗时极长,不建议)
        self.providers = providers or []
        # 单次(单个节点)检测的总超时时间(秒)
        self.timeout = timeout
        # Go 侧并发数(MediaUnlockTest 会并行测试多个服务)
        self.conc = conc

    async def test(self, proxy_url: str) -> List[Dict[str, Any]]:
        """对指定代理执行流媒体解锁测试,返回结构化结果列表。

        Args:
            proxy_url: 代理 URL,如 http://127.0.0.1:7890

        Returns:
            检测结果列表;任何失败/超时返回空列表(调用方需容忍)
        """
        if not proxy_url:
            logger.warning("未提供代理 URL,跳过流媒体解锁检测")
            return []
        if not os.path.exists(self.binary_path):
            logger.warning("MediaUnlockTest 二进制不存在: %s,跳过流媒体解锁检测", self.binary_path)
            return []

        # 组装命令行参数
        cmd = [
            self.binary_path,
            "-json",                      # JSON 结构化输出
            "-http-proxy", proxy_url,     # 走当前 Clash 节点代理
            "-show-active=false",         # 不显示进度条描述(减少 stderr 输出)
            "-conc", str(self.conc),      # 并发数
        ]
        if self.providers:
            cmd += ["-providers", ",".join(self.providers)]

        proc = None
        try:
            # 异步启动子进程,避免阻塞事件循环
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)

            if proc.returncode != 0:
                # 非零退出码,记录 stderr 末尾内容便于排查
                err_tail = err.decode(errors="ignore")[-500:]
                logger.error("mediatest 退出码 %s: %s", proc.returncode, err_tail)
                return []

            data = json.loads(out.decode(errors="ignore"))
            if not isinstance(data, list):
                logger.error("mediatest 输出不是 JSON 数组: %r", out[:200])
                return []
            return data

        except asyncio.TimeoutError:
            # 单节点检测超时,强制终止子进程
            logger.error("mediatest 超时(>%ss),已终止", self.timeout)
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass
            return []
        except json.JSONDecodeError as e:
            logger.error("mediatest JSON 解析失败: %s", e)
            return []
        except Exception as e:
            logger.error("mediatest 执行失败: %s", e)
            return []

    @staticmethod
    def _abbr(name: str) -> str:
        """获取服务名对应的短缩写(未映射则截取前 6 个字符)。"""
        return PROVIDER_ABBR.get(name, name[:6])

    @staticmethod
    def _status_symbol(item: Dict[str, Any]) -> str:
        """根据状态返回标注符号与地区后缀。"""
        status = item.get("status_text", "unknown")
        region = item.get("region", "")
        if status == "ok":
            return f"✓({region})" if region else "✓"
        if status == "restricted":
            return f"⚠({region})" if region else "⚠"
        return "✗"

    def format_summary(self, results: List[Dict[str, Any]]) -> str:
        """把检测结果压缩为节点名标注用的短摘要(只保留解锁成功的服务)。

        例: "GM✓(sg)·NF✓(us)·GPT✓" — 解锁失败(✗)的服务不显示。
        """
        if not results:
            return ""
        parts = []
        for item in results:
            if item.get("status_text") != "ok":
                # 只放解锁的,不放不解锁的
                continue
            name = item.get("name", "?")
            abbr = self._abbr(name)
            parts.append(f"{abbr}{self._status_symbol(item)}")
        return "·".join(parts)
