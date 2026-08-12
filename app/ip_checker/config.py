import os
from typing import List

class Config:
    def __init__(self):
        # Clash API配置
        self.api_url = os.getenv("CLASH_API_URL", "http://127.0.0.1:9090")
        self.api_secret = os.getenv("CLASH_API_SECRET", "")
        
        # 检测配置
        self.max_queue_size = int(os.getenv("MAX_QUEUE_SIZE", "10"))
        self.max_age = int(os.getenv("MAX_AGE", "360"))  # 缓存有效期(秒)
        self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "10"))  # 每个节点检测的超时时间(秒)
        self.source = os.getenv("SOURCE", "ping0")  # 优先数据源
        self.fallback = os.getenv("FALLBACK", "true").lower() == "true"  # 主源失败时是否尝试备用源
        
        # 跳过关键词
        self.skip_keywords = os.getenv("SKIP_KEYWORDS", "剩余,重置,到期,有效期,官网,网址,更新,公告,建议").split(",")
        
        # API基础URL
        self.api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
        
        # 数据目录
        self.data_dir = os.getenv("DATA_DIR", os.path.join(os.getcwd(), "data"))
        os.makedirs(self.data_dir, exist_ok=True)

config = Config()