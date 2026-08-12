import asyncio
import logging
from typing import List, Dict, Any, Optional
from .providers import load_providers

logger = logging.getLogger("TesterService")

class TesterService:
    def __init__(self, providers: List[str], proxy: str = None):
        self.providers = load_providers(providers)
        self.proxy = proxy
        self.results = {}
    
    async def test_stream(self, provider_names: List[str], proxy: str = None) -> Dict[str, Any]:
        """
        测试流媒体解锁情况
        
        Args:
            provider_names: 流媒体提供商名称列表
            proxy: 代理URL
            
        Returns:
            测试结果的字典
        """
        proxy_to_use = proxy or self.proxy
        
        # 并行测试所有提供商
        tasks = []
        for provider_name in provider_names:
            if provider_name in self.providers:
                provider = self.providers[provider_name]
                task = self._test_single_provider(provider, proxy_to_use)
                tasks.append(task)
        
        # 等待所有测试完成
        results = await asyncio.gather(*tasks)
        
        # 整理结果
        final_results = {
            "timestamp": datetime.datetime.now().isoformat(),
            "total_providers": len(provider_names),
            "successful_tests": sum(1 for r in results if r["success"]),
            "failed_tests": sum(1 for r in results if not r["success"]),
            "details": results
        }
        
        return final_results
    
    async def _test_single_provider(self, provider, proxy: str = None) -> Dict[str, Any]:
        """
        测试单个流媒体提供商
        
        Args:
            provider: 流媒体提供商对象
            proxy: 代理URL
            
        Returns:
            测试结果的字典
        """
        try:
            # 使用代理测试
            result = await provider.test(proxy=proxy)
            
            return {
                "provider": provider.name,
                "success": result["success"],
                "region": result.get("region", "unknown"),
                "message": result.get("message", ""),
                "details": result.get("details", {}),
                "response_time": result.get("response_time", 0),
                "timestamp": datetime.datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to test provider {provider.name}: {e}")
            return {
                "provider": provider.name,
                "success": False,
                "region": "unknown",
                "message": str(e),
                "details": {},
                "response_time": 0,
                "timestamp": datetime.datetime.now().isoformat()
            }
    
    def get_supported_providers(self) -> List[str]:
        """获取支持的流媒体提供商列表"""
        return list(self.providers.keys())
    
    def get_provider_info(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """获取指定提供商的信息"""
        if provider_name in self.providers:
            provider = self.providers[provider_name]
            return {
                "name": provider.name,
                "description": provider.description,
                "url": provider.url,
                "regions": provider.regions
            }
        return None
    
    async def batch_test(self, providers: List[str], proxy: str = None) -> Dict[str, Any]:
        """
        批量测试流媒体提供商
        
        Args:
            providers: 流媒体提供商名称列表
            proxy: 代理URL
            
        Returns:
            批量测试结果的字典
        """
        return await self.test_stream(providers, proxy=proxy)