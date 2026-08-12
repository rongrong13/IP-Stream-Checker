from typing import Dict, Any, List
import importlib
import os

class Provider:
    def __init__(self, name: str, description: str, url: str, regions: List[str]):
        self.name = name
        self.description = description
        self.url = url
        self.regions = regions
    
    async def test(self, proxy: str = None) -> Dict[str, Any]:
        """测试流媒体解锁情况"""
        raise NotImplementedError("Subclasses must implement this method")

def load_providers(provider_names: List[str]) -> Dict[str, Provider]:
    """加载指定的流媒体提供商"""
    providers = {}
    
    # 默认支持的提供商
    default_providers = {
        "netflix": {
            "name": "Netflix",
            "description": "Netflix流媒体服务",
            "url": "https://www.netflix.com",
            "regions": ["US", "JP", "KR", "UK", "CA", "AU", "DE", "FR", "IT", "ES"]
        },
        "hulu": {
            "name": "Hulu",
            "description": "Hulu流媒体服务",
            "url": "https://www.hulu.com",
            "regions": ["US"]
        },
        "disneyplus": {
            "name": "Disney+",
            "description": "Disney+流媒体服务",
            "url": "https://www.disneyplus.com",
            "regions": ["US", "JP", "KR", "UK", "CA", "AU", "DE", "FR", "IT", "ES"]
        },
        "primevideo": {
            "name": "Prime Video",
            "description": "Amazon Prime Video流媒体服务",
            "url": "https://www.primevideo.com",
            "regions": ["US", "JP", "KR", "UK", "CA", "AU", "DE", "FR", "IT", "ES"]
        }
    }
    
    # 加载默认提供商
    for name, config in default_providers.items():
        if name in provider_names:
            providers[name] = Provider(**config)
    
    return providers

# 动态加载额外的提供商模块
def load_additional_providers() -> Dict[str, Provider]:
    """加载额外的流媒体提供商模块"""
    providers = {}
    
    # 查找providers目录中的所有.py文件
    providers_dir = os.path.dirname(__file__)
    for filename in os.listdir(providers_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            try:
                module = importlib.import_module(f"app.stream_tester.providers.{module_name}")
                if hasattr(module, "provider"):
                    providers[module_name] = module.provider
            except ImportError as e:
                print(f"Failed to load provider {module_name}: {e}")
    
    return providers