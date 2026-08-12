from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.ip_checker.checker_service import CheckerService
from app.stream_tester.tester_service import TesterService
import yaml
import os

# 初始化FastAPI应用
app = FastAPI(title="IP-Stream-Checker", description="流媒体解锁与IP风险检测工具")

# 配置模板和静态文件
templates = Jinja2Templates(directory="app/web/templates")
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

# 加载配置
with open("config/config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# 初始化服务
ip_checker = CheckerService(
    api_url=config.get("clash_api_url", "http://127.0.0.1:9090"),
    api_secret=config.get("clash_api_secret", "")
)

stream_tester = TesterService(
    providers=config.get("stream_providers", []),
    proxy=config.get("proxy", "")
)

@app.get("/")
async def index(request: Request):
    """主页 - 显示测试选项和结果"""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "IP-Stream-Checker"}
    )

@app.post("/api/ip-check")
async def ip_check(url: str, source: str = "ping0", timeout: int = 10):
    """IP-risk检测API"""
    result = await ip_checker.check_ip(url, source=source, timeout=timeout)
    return {"status": "success", "data": result}

@app.post("/api/stream-test")
async def stream_test(providers: list, proxy: str = None):
    """流媒体解锁测试API"""
    results = await stream_tester.test_stream(providers, proxy=proxy)
    return {"status": "success", "data": results}

@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "services": ["ip_checker", "stream_tester"]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)