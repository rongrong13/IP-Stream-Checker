import asyncio
import os
import shutil
import yaml
import logging
import datetime
from typing import Optional, Dict, Any
from curl_cffi.requests import AsyncSession
from .clash_api import ClashController
from .config import config
from .sources.ippure import IPPureSource
from .sources.ping0 import Ping0Source

# Configure logging
logger = logging.getLogger("CheckerService")

class CheckerService:
    def __init__(self, api_url: str = None, api_secret: str = ""):
        # If no api_url provided, use config
        self.api_url = api_url or config.api_url
        self.clash = ClashController(self.api_url, api_secret)
        self.current_file = None
        self.SKIP_KEYWORDS = config.skip_keywords
        
    async def check_ip(self, proxy_url: str, source: str = "ping0", timeout: int = 10) -> Dict[str, Any]:
        """
        检查IP风险和质量
        
        Args:
            proxy_url: 代理URL
            source: 数据源 (ping0/ippure)
            timeout: 超时时间(秒)
            
        Returns:
            检测结果的字典
        """
        options = {
            "source": source,
            "timeout": timeout,
            "fallback": config.fallback
        }
        
        # Initialize sources
        sources = {
            "ippure": IPPureSource(),
            "ping0": Ping0Source()
        }
        
        # Determine Order from options or config
        primary_name = options.get("source") or config.source
        allow_fallback = options.get("fallback") if options.get("fallback") is not None else config.fallback
        
        # Get primary source
        primary_source = sources.get(primary_name)
        if not primary_source:
            raise ValueError(f"Unknown source: {primary_name}")
        
        # Check IP using primary source
        result = await primary_source.check(proxy_url, timeout=timeout)
        
        # If primary source fails and fallback is enabled, try secondary source
        if not result["success"] and allow_fallback and primary_name != "ippure":
            secondary_source = sources.get("ippure")
            if secondary_source:
                result = await secondary_source.check(proxy_url, timeout=timeout)
        
        return result
    
    async def check_subscription(self, subscription_url: str) -> Dict[str, Any]:
        """
        检查订阅链接的质量
        
        Args:
            subscription_url: 订阅URL
            
        Returns:
            检测结果的字典
        """
        # 解析订阅URL
        parsed_url = urlparse(subscription_url)
        query_params = parse_qs(parsed_url.query)
        
        # 检查是否有代理URL参数
        proxy_url = query_params.get("url", [None])[0]
        if not proxy_url:
            raise ValueError("Missing proxy URL in subscription link")
        
        # 检查IP
        ip_result = await self.check_ip(proxy_url)
        
        # 返回包含原始订阅URL的结果
        return {
            "status": "success",
            "original_url": subscription_url,
            "proxy_url": proxy_url,
            "ip_check": ip_result,
            "timestamp": datetime.datetime.now().isoformat()
        }
    
    async def batch_check(self, proxy_urls: list) -> list:
        """
        批量检查多个代理
        
        Args:
            proxy_urls: 代理URL列表
            
        Returns:
            检测结果列表
        """
        tasks = [self.check_ip(url) for url in proxy_urls]
        results = await asyncio.gather(*tasks)
        return results
    
    def generate_subscription_link(self, original_url: str, source: str = "ping0") -> str:
        """
        生成带有检测功能的订阅链接
        
        Args:
            original_url: 原始订阅URL
            source: 数据源
            
        Returns:
            新的订阅链接
        """
        base_url = f"{config.api_base_url}/check"
        params = {
            "url": original_url,
            "source": source
        }
        return f"{base_url}?{urlencode(params)}"