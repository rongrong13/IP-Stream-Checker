import asyncio
import logging
from typing import Dict, Any
from curl_cffi.requests import AsyncSession
from ..providers import Provider

logger = logging.getLogger("NetflixProvider")

class NetflixProvider(Provider):
    def __init__(self):
        super().__init__(
            name="netflix",
            description="Netflix流媒体服务",
            url="https://www.netflix.com",
            regions=["US", "JP", "KR", "UK", "CA", "AU", "DE", "FR", "IT", "ES"]
        )
    
    async def test(self, proxy: str = None) -> Dict[str, Any]:
        """
        测试Netflix解锁情况
        
        Args:
            proxy: 代理URL
            
        Returns:
            测试结果的字典
        """
        try:
            session = AsyncSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1"
                },
                timeout=15,
                impersonate="chrome110"
            )
            
            # 设置代理
            proxies = {}
            if proxy:
                proxies = {
                    "http": proxy,
                    "https": proxy
                }
            
            # 发送请求
            response = await session.get(
                self.url,
                proxies=proxies,
                allow_redirects=True
            )
            
            # 检查响应
            if response.status_code == 200:
                content = response.text
                
                # 检查是否是Netflix主页
                if "Netflix" in content and "Sign In" in content:
                    # 尝试获取地区信息
                    region = self._detect_region(content)
                    
                    return {
                        "success": True,
                        "region": region,
                        "message": f"Netflix accessible in {region}",
                        "details": {
                            "status_code": response.status_code,
                            "response_time": response.elapsed.total_seconds(),
                            "content_length": len(content)
                        },
                        "response_time": response.elapsed.total_seconds()
                    }
                else:
                    return {
                        "success": False,
                        "region": "unknown",
                        "message": "Not a valid Netflix page",
                        "details": {
                            "status_code": response.status_code,
                            "response_time": response.elapsed.total_seconds()
                        },
                        "response_time": response.elapsed.total_seconds()
                    }
            else:
                return {
                    "success": False,
                    "region": "unknown",
                    "message": f"HTTP {response.status_code}",
                    "details": {
                        "status_code": response.status_code,
                        "response_time": response.elapsed.total_seconds()
                    },
                    "response_time": response.elapsed.total_seconds()
                }
                
        except Exception as e:
            logger.error(f"Netflix test failed: {e}")
            return {
                "success": False,
                "region": "unknown",
                "message": str(e),
                "details": {},
                "response_time": 0
            }
    
    def _detect_region(self, content: str) -> str:
        """
        从页面内容中检测地区信息
        
        Args:
            content: 页面HTML内容
            
        Returns:
            检测到的地区
        """
        # 简单的地区检测逻辑
        if "Netflix US" in content or "United States" in content:
            return "US"
        elif "Netflix Japan" in content or "Japan" in content:
            return "JP"
        elif "Netflix Korea" in content or "Korea" in content:
            return "KR"
        elif "Netflix UK" in content or "United Kingdom" in content:
            return "UK"
        elif "Netflix Canada" in content or "Canada" in content:
            return "CA"
        elif "Netflix Australia" in content or "Australia" in content:
            return "AU"
        elif "Netflix Germany" in content or "Germany" in content:
            return "DE"
        elif "Netflix France" in content or "France" in content:
            return "FR"
        elif "Netflix Italy" in content or "Italy" in content:
            return "IT"
        elif "Netflix Spain" in content or "Spain" in content:
            return "ES"
        else:
            return "unknown"