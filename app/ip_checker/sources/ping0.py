import asyncio
import logging
from typing import Dict, Any
from curl_cffi.requests import AsyncSession

logger = logging.getLogger("Ping0Source")

class Ping0Source:
    def __init__(self):
        self.session = AsyncSession(
            headers={"User-Agent": "Clash-IP-Checker/1.0"},
            timeout=10,
            impersonate="chrome110"
        )
    
    async def check(self, proxy_url: str, timeout: int = 10) -> Dict[str, Any]:
        """
        使用ping0 API检查IP
        
        Args:
            proxy_url: 代理URL
            timeout: 超时时间(秒)
            
        Returns:
            检测结果的字典
        """
        try:
            # 构建ping0 API URL
            ping0_url = f"https://ping0.cc/ip"
            
            # 设置代理
            proxies = {
                "http": proxy_url,
                "https": proxy_url
            }
            
            # 发送请求
            response = await self.session.get(
                ping0_url,
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
                    "asn": ip_info.get("asn"),
                    "isp": ip_info.get("isp"),
                    "type": "datacenter" if ip_info.get("type") == "datacenter" else "residential",
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
            logger.error(f"Ping0 check failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "response_time": 0
            }