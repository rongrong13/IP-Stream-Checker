import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("ClashController")

class ClashController:
    def __init__(self, api_url: str, api_secret: str = ""):
        self.api_url = api_url.rstrip('/')
        self.api_secret = api_secret
        self.headers = {}
        
        if api_secret:
            self.headers["Authorization"] = f"Bearer {api_secret}"
    
    def get_proxies(self) -> Dict[str, Any]:
        """获取所有代理"""
        url = f"{self.api_url}/proxies"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get proxies: {e}")
            return {}
    
    def get_proxy(self, name: str) -> Dict[str, Any]:
        """获取指定代理"""
        url = f"{self.api_url}/proxies/{name}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get proxy {name}: {e}")
            return {}
    
    def set_proxy(self, name: str, proxy: Dict[str, Any]) -> bool:
        """设置代理配置"""
        url = f"{self.api_url}/proxies/{name}"
        try:
            response = requests.put(url, json=proxy, headers=self.headers)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to set proxy {name}: {e}")
            return False
    
    def test_proxy(self, name: str) -> Dict[str, Any]:
        """测试代理连通性"""
        url = f"{self.api_url}/proxies/{name}/test"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to test proxy {name}: {e}")
            return {"success": False, "error": str(e)}
    
    def get_traffic(self) -> Dict[str, Any]:
        """获取流量统计"""
        url = f"{self.api_url}/traffic"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get traffic: {e}")
            return {}
    
    def get_logs(self, level: str = "info", lines: int = 100) -> List[str]:
        """获取日志"""
        url = f"{self.api_url}/logs?level={level}&lines={lines}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json().get("logs", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get logs: {e}")
            return []
    
    def get_version(self) -> str:
        """获取Clash版本"""
        url = f"{self.api_url}/version"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json().get("version", "unknown")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get version: {e}")
            return "unknown"