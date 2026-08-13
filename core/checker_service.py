import asyncio
import os
import random
import shutil
import yaml
import logging
import datetime
from typing import Optional
from curl_cffi.requests import AsyncSession
from .clash_api import ClashController
from .config import config
from stream_tester.media_unlock import MediaUnlockTester

# Configure logging
# logging.basicConfig removed
logger = logging.getLogger("CheckerService")

# 自动降级(allow_fallback=True)时可选的备用数据源池。
# ping0/ippure 已被 Cloudflare 拦截或官方 API 失效,若作为自动 fallback,
# 每个检测失败的节点都要白白等待其超时(约 30-45s),故自动降级只回落到当前可用的源。
# 手动选择 ping0/ippure 作为主源时,仍可用 ipapi 兜底。
FALLBACK_POOL = ["ipapi"]

class CheckerService:
    def __init__(self, api_url: str = None, api_secret: str = ""):
        # If no api_url provided, use config
        self.api_url = api_url or config.api_url
        self.clash = ClashController(self.api_url, api_secret)
        self.current_file = None
        self.SKIP_KEYWORDS = config.skip_keywords

        # 初始化流媒体解锁检测器(整合 MediaUnlockTest)
        st_cfg = config.stream_test
        if st_cfg["enabled"]:
            self.stream_tester = MediaUnlockTester(
                binary_path=st_cfg["binary_path"],
                providers=st_cfg["providers"],
                timeout=st_cfg["timeout"],
                conc=st_cfg["conc"],
            )
            self.stream_node_label = st_cfg["node_label"]
            print(f"[INFO] 流媒体解锁检测已启用: {st_cfg['providers']}", flush=True)
        else:
            self.stream_tester = None
            self.stream_node_label = False

    async def _check_stream(self, proxy_url: str) -> list:
        """对当前代理执行流媒体解锁检测,任何失败返回空列表(不影响主流程)。"""
        try:
            return await self.stream_tester.test(proxy_url)
        except Exception as e:
            print(f"     [StreamTest] Error: {e}", flush=True)
            return []
        
    async def _check_ip_fast(self, proxy_url: str, options: dict = None):
        """
        Checks IP using configured sources with fallback.
        """
        from .sources.ippure import IPPureSource
        from .sources.ping0 import Ping0Source
        from .sources.ipapi import IpApiSource
        
        options = options or {}

        # Initialize sources
        sources = {
            "ippure": IPPureSource(),
            "ping0": Ping0Source(),
            "ipapi": IpApiSource()
        }
        
        # Determine Order from options or config
        primary_name = options.get("source") or config.source
        allow_fallback = options.get("fallback") if options.get("fallback") is not None else config.fallback
        request_timeout = options.get("request_timeout") or config.request_timeout

        # 按主源 + 降级池构建检测顺序(自动降级只回落到当前可用源,避免白等已失效源)
        order_names = self._build_source_order(primary_name, allow_fallback, set(sources.keys()))
        ordered_sources = [sources[n] for n in order_names if n in sources]
        if not ordered_sources:
            ordered_sources = [sources["ping0"], sources["ippure"]]

        last_error = None
        
        for source in ordered_sources:
            try:
                # Pass timeout via specific mechanism if source supports it?
                # Currently sources import 'config' global.
                # To trigger per-request timeout without rewriting all sources, 
                # we might need to rely on sources reading a contextual config or accept kwargs.
                # Let's check BaseSource again. It takes (proxy_url).
                # I'll update BaseSource later or hack it here?
                # For now let's focus on source selection logic which IS here.
                
                res = await source.check(proxy_url, timeout=request_timeout)
                
                if res.get("error"):
                    last_error = res["error"]
                    continue
                
                return res
            except Exception as e:
                last_error = str(e)
                continue
        
        return {
            "pure_emoji": "⚫", "ip_attr": "未知", "ip_src": "未知",
            "pure_score": "?", "ip": "?", 
            "error": f"All sources failed. Last: {last_error}"
        }

    @staticmethod
    def _build_source_order(primary_name: str, allow_fallback: bool, available: set) -> list:
        """构建数据源检测顺序: 主源在前,降级时追加当前可用源(FALLBACK_POOL)。

        ping0/ippure 已被 Cloudflare 拦截或 API 失效,不作为自动降级目标;
        手动选择它们作为主源时,仍可用 ipapi 兜底。
        """
        ordered = []
        if primary_name in available:
            ordered.append(primary_name)
        if allow_fallback:
            for name in FALLBACK_POOL:
                if name != primary_name and name in available:
                    ordered.append(name)
        if not ordered:
            ordered = ["ping0", "ippure"]
        return ordered

    def _strip_old_tag(self, name: str) -> str:
        """去除节点名中已有的检测标注 【...】"""
        import re
        return re.sub(r'\s*【[^】]*】', '', name).strip()

    @staticmethod
    def _parse_score(score) -> float:
        """把风险度字符串(如 '61%')解析为数值;解析失败返回 None。"""
        if not score:
            return None
        try:
            return float(str(score).replace('%', '').strip())
        except (ValueError, TypeError):
            return None

    def _format_name(self, old_name: str, res: dict, stream_label: str = "") -> str:
        """按新格式重命名节点:
        {原节点名}·{风险度%}·{流媒体解锁摘要}{IP标注}
        例: 🇭🇰 HK-01·61%·GM✓(sg)·NF✓(us)·GPT✓【🟢 住宅|原生】
        """
        # 先去掉已有的标注
        base_name = self._strip_old_tag(old_name)

        if res["error"]:
            return f"{base_name} 【❌ 失败】"

        # 1. 风险度百分比(污染度)
        score = res.get("pure_score")
        if score in (None, "", "?", "❓"):
            score = ""

        # 2. IP 检测标注(直接拼接在末尾,不加分隔符)
        if "full_string" in res and res["full_string"]:
            # ping0 返回形如 【🟢⚪ 住宅|原生】
            ip_tag = res["full_string"]
        else:
            info = f"{res['ip_attr']}|{res['ip_src']}"
            ip_tag = f"【{res['pure_emoji']} {info}】"

        # 主体部分(节点名·风险度·流媒体解锁摘要)用 · 连接,空项跳过
        prefix = "·".join(p for p in (base_name, str(score), stream_label) if p)
        return prefix + ip_tag

    async def async_atomic_save(self, data: dict, file_path: str):
        """Async wrapper for atomic save."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.atomic_save, data, file_path)

    def atomic_save(self, data: dict, file_path: str):
        """Saves YAML to .tmp and renames to target."""
        tmp_path = f"{file_path}.tmp"
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            os.replace(tmp_path, file_path)
        except Exception as e:
            print(f"LOG: Failed to save atomic YAML: {e}", flush=True)

    async def run_check(self, file_path: str, progress_cb=None, options: dict = None, stop_event=None):
        """
        Main orchestration function.
        options: dict of runtime overrides (skip_keywords, etc)
        stop_event: asyncio.Event to signal cancellation
        """
        options = options or {}
        
        self.current_file = file_path
        try:
            # 1. Wait for API
            if not await self.clash.version():
                raise ConnectionError("Clash API unreachable. Is the backend running?")

            # 2. Get absolute path for Clash (Docker: mapped paths must work)
            abs_path = os.path.abspath(file_path)
            if not await self.clash.load_config(abs_path):
                raise ValueError("Failed to load config into Clash. Check YAML syntax.")
            
            await asyncio.sleep(1) # Wait reload
            
            # Enforce Port 7890
            await self.clash.update_ports(config.mixed_port)
            
            if await self.clash.set_mode_global():
                print("[INFO] Switched to Global Mode", flush=True)
            else:
                print("[WARN] Failed to switch to Global Mode", flush=True)
            
            port = await self.clash.get_mixed_port()
            proxy_url = f"http://127.0.0.1:{port}"
            
            # 3. Get Proxies
            all_proxies = await self.clash.get_proxies()
            if not all_proxies:
                raise ValueError("No proxies found in the configuration.")

            # Parse local YAML to preserve structure and update names in place
            with open(file_path, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f)
            
            # Create a map for fast lookup of YAML proxy objects
            yaml_proxies = yaml_data.get('proxies', [])
            
            total = len(yaml_proxies)
            checked_count = 0
            
            # Initial Progress Report
            if progress_cb:
                await progress_cb(0, total, "Starting...")
            
            # Get Config Values (Runtime Override or Global)
            skip_keywords = options.get("skip_keywords") or self.SKIP_KEYWORDS
            # 风险节点过滤阈值(风险度超过该值的节点从输出中移除, 0 = 不过滤)
            risk_threshold = options.get("filter_risk_threshold", config.filter_risk_threshold)
            # 记录因风险过高被移除的节点名,循环结束后统一从输出中删除
            removed_risky = []

            # ---- 节点测活(借鉴 subs-check): 用 Mihomo 内核并发测活,提前剔除不可用节点 ----
            # 不可用节点不进入 IP 检测/流媒体检测阶段,避免白白等待超时,显著加速大订阅。
            dead_nodes = set()
            alive_cfg = config.alive_test
            if alive_cfg["enabled"] and yaml_proxies:
                if progress_cb:
                    await progress_cb(0, total, "节点测活中(内核并发)...")
                print(f"[INFO] Testing liveness for {total} nodes via Mihomo group delay...", flush=True)
                alive_map = await self.clash.test_group_delay(
                    group="GLOBAL",
                    url=alive_cfg["url"],
                    timeout_ms=alive_cfg["timeout_ms"],
                )
                if alive_map:
                    # 只对真正要检测的节点(非 skip 关键词)判断存活
                    dead_nodes = {
                        p["name"] for p in yaml_proxies
                        if not any(k in p["name"] for k in skip_keywords)
                        and p["name"] not in alive_map
                    }
                    alive_count = len(yaml_proxies) - len(dead_nodes)
                    print(f"[INFO] Alive: {alive_count}, Dead: {len(dead_nodes)}", flush=True)
                    if progress_cb and dead_nodes:
                        await progress_cb(0, total, f"测活完成: 存活 {alive_count}, 不可用 {len(dead_nodes)}")
                else:
                    # 测活接口不可用(如内核不支持): 安全降级为全部存活
                    print("[WARN] 测活接口无返回,跳过测活(全部按存活处理)", flush=True)
            dead_policy = alive_cfg["dead_policy"] if alive_cfg["enabled"] else "skip"

            # ---- 打乱测试顺序(借鉴 subs-check shuffle-test-order): 只影响测试先后,输出保持原序 ----
            order = list(range(len(yaml_proxies)))
            if config.shuffle_test_order and len(order) > 1:
                random.shuffle(order)

            for idx in order:
                p_config = yaml_proxies[idx]
                # Check cancellation
                if stop_event and stop_event.is_set():
                    print("[INFO] Check cancelled by user.", flush=True)
                    if progress_cb:
                        await progress_cb(checked_count, total, "Cancelled by user.")
                    break

                name = p_config['name']
                
                # Filter invalid nodes
                if any(k in name for k in skip_keywords):
                     checked_count += 1
                     if progress_cb:
                        await progress_cb(checked_count, total, f"Skipped: {name}")
                     continue

                # 不可用节点(测活未通过): 按策略跳过或移除
                if name in dead_nodes:
                    checked_count += 1
                    if dead_policy == "remove":
                        removed_risky.append(name)
                        print(f"       => [已移除] {name} (测活不可用)", flush=True)
                        if progress_cb:
                            await progress_cb(checked_count, total, f"已移除不可用节点: {name}")
                    else:
                        print(f"       => [已跳过] {name} (测活不可用)", flush=True)
                        if progress_cb:
                            await progress_cb(checked_count, total, f"跳过不可用节点: {name}")
                    continue

                # Use clean name for logging to avoid confusion with old results
                display_name = self._strip_old_tag(name)
                
                # Switch
                print(f"[INFO] Checking [{idx+1}/{total}]: {display_name}", flush=True)
                if progress_cb:
                    await progress_cb(checked_count, total, f"Checking: {display_name}")

                if await self.clash.switch_proxy(name):
                    # Check
                    await asyncio.sleep(0.5) # Wait switch
                    res = await self._check_ip_fast(proxy_url, options=options)

                    # 风险节点过滤: 风险度超过阈值的节点从输出中移除(方便直接导入 OpenClash)
                    if risk_threshold and risk_threshold > 0 and not res.get("error"):
                        score_val = self._parse_score(res.get("pure_score"))
                        if score_val is not None and score_val > risk_threshold:
                            removed_risky.append(name)
                            checked_count += 1
                            print(f"       => [已移除] {display_name} (风险度 {res.get('pure_score')} > {risk_threshold}%)", flush=True)
                            if progress_cb:
                                await progress_cb(checked_count, total,
                                    f"已移除风险节点: {display_name} (风险 {res.get('pure_score')} > {risk_threshold}%)")
                            continue

                    # 流媒体解锁检测(整合 MediaUnlockTest):
                    # 仅当 IP 检测成功(节点可用)时执行,避免无效节点拖慢整个任务
                    stream_label = ""
                    if self.stream_tester and not res.get("error"):
                        stream_results = await self._check_stream(proxy_url)
                        if self.stream_node_label:
                            stream_label = self.stream_tester.format_summary(stream_results)

                    # Update Name
                    new_name = self._format_name(name, res, stream_label)
                    print(f"       => {new_name}", flush=True)
                    p_config['name'] = new_name
                    
                    # Update in proxy-groups
                    if 'proxy-groups' in yaml_data:
                        for g in yaml_data['proxy-groups']:
                            if 'proxies' in g:
                                g['proxies'] = [new_name if pn == name else pn for pn in g['proxies']]

                    # ATOMIC WRITE execution (Batch Save)
                    checked_count += 1
                    if checked_count % 5 == 0:
                         await self.async_atomic_save(yaml_data, file_path)
                         print(f"[INFO] Intermediate Save at {checked_count}/{total}", flush=True)
                    
                    # Notify UI of result
                    if progress_cb:
                        # Show detailed result in logs with Shared Count
                        shared_info = ""
                        if res.get('shared_users') and res.get('shared_users') != "N/A":
                            shared_info = f"  共享: {res['shared_users']}"
                        
                        # 追加流媒体解锁摘要(如有)
                        stream_info = ""
                        if stream_label:
                            stream_info = f"  {stream_label.strip()}"
                        
                        log_msg = f"Result: IP: {res['ip']}  污染度: {res['pure_score']}{shared_info}  {res['ip_attr']} {res['ip_src']}{stream_info}"
                        await progress_cb(checked_count, total, log_msg)
                    
                    # Also print to console
                    shared_log = f" | 共享: {res.get('shared_users')}" if res.get('shared_users') and res.get('shared_users') != "N/A" else ""
                    print(f"       => IP: {res['ip']} | 污染度: {res['pure_score']}{shared_log} | {res['ip_attr']} | {res['ip_src']}{stream_label}", flush=True)
                else:
                    print(f"[WARN] Could not switch to {name}", flush=True)
                    checked_count += 1  # 即使失败也要计数，保证进度条准确
                    if progress_cb:
                        await progress_cb(checked_count, total, f"Error: Could not switch to {display_name}")

            # 统一移除风险过高的节点(从 proxies 与 proxy-groups 中删除)
            if removed_risky:
                yaml_data['proxies'] = [p for p in yaml_data.get('proxies', []) if p.get('name') not in removed_risky]
                for g in yaml_data.get('proxy-groups', []):
                    if 'proxies' in g:
                        g['proxies'] = [pn for pn in g['proxies'] if pn not in removed_risky]
                print(f"[FILTER] 已移除 {len(removed_risky)} 个风险过高节点: {removed_risky}", flush=True)
                if progress_cb:
                    await progress_cb(checked_count, total, f"已移除 {len(removed_risky)} 个风险过高节点")

            # Debug: Verify modification before final save? 
            await self.async_atomic_save(yaml_data, file_path) # Force final save
            print(f"[INFO] Check complete. Final save to {file_path}", flush=True)


            # Mark completion (e.g. modify a comment or a metadata field? Or just rely on file mtime)
            print("[INFO] Check complete.", flush=True)

        except Exception as e:
            print(f"[ERROR] Global Check Error: {e}", flush=True)
            raise e
        finally:
            self.current_file = None
