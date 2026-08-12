import asyncio
import logging
from typing import Dict, Any
from curl_cffi.requests import AsyncSession

logger = logging.getLogger("IPPureSource")

class IPPureSource:
    def __init__(self):
        self.session = AsyncSession(
            headers={"User-Agent": "Clash-IP-Checker/1.0"},
            timeout=10,
            impersonate="chrome110"
        )
    
    async def check(self, proxy_url: str, timeout: int = 10) -> Dict[str, Any]:
        """
        使用ippure API检查IP
        
        Args:
            proxy_url: 代理URL
            timeout: 超时时间(秒)
            
        Returns:
            检测结果的字典
        """
        try:
            # 构建ippure API URL
            ippure_url = "https://api.ippure.net/ip"
            
            # 设置代理
            proxies = {
                "http": proxy_url,
                "https": proxy_url
            }
            
            # 发送请求
            response = await self.session.get(
                ippure_url,
                proxies=proxies,
                timeout=timeout
            )
            
            if response.status_code == 200:
                ip_info = response.json()
                return {
                    "success": True,
                    "ip": ip_info.get("ip"),
                    "country": ip_info.get("country"),
                    "city": ip_info.get("city"),
                    "region": ip_info.get("region"),
                    "isp": ip_info.get("isp"),
                    "type": ip_info.get("type", "unknown"),
                    "response_time": response.elapsed.total_seconds(),
                    "timestamp": datetime.datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "response_time": response.elapsed.total_seconds()
                }
                
        except Exception as e:
            logger.error(f"IPPure check failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "response_time": 0
            }