from contextlib import asynccontextmanager

import hashlib
import os
import time
import requests
import asyncio
import logging
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from core.checker_service import CheckerService
from core.config import config
import yaml
import json
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Job Manager Worker...")
    await job_manager.start_worker()
    # 启动时清理一次过期的检测结果文件(按 result_retention_days)
    try:
        await asyncio.to_thread(cleanup_old_results)
        asyncio.create_task(cleanup_loop())
    except Exception as e:
        print(f"[WARN] 初始化结果清理任务失败: {e}", flush=True)
    yield
    # Shutdown logic if needed

app = FastAPI(lifespan=lifespan)


def cleanup_old_results():
    """清理超过 result_retention_days 天的结果文件与失效的历史记录。

    结果文件存放在 DATA_DIR(挂载卷)中,按文件修改时间判断是否过期。
    result_retention_days = 0 表示永久保留。
    """
    days = config.result_retention_days
    if days <= 0:
        return
    cutoff = time.time() - days * 86400
    removed_files = 0
    try:
        for fname in os.listdir(DATA_DIR):
            if not fname.endswith(('.yaml', '.map')):
                continue
            fpath = os.path.join(DATA_DIR, fname)
            try:
                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    removed_files += 1
            except Exception:
                pass
    except Exception as e:
        print(f"[WARN] 清理结果文件失败: {e}", flush=True)
    # 移除历史记录中结果文件已不存在的条目
    pruned = 0
    try:
        pruned = history_store.prune_missing_files()
    except Exception as e:
        print(f"[WARN] 清理历史记录失败: {e}", flush=True)
    print(f"[CLEANUP] 已清理 {removed_files} 个过期结果文件、{pruned} 条失效历史(>{days}天)", flush=True)


async def cleanup_loop():
    """后台定时清理任务: 每 24 小时执行一次。"""
    while True:
        try:
            await asyncio.sleep(86400)
            await asyncio.to_thread(cleanup_old_results)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[WARN] 定时清理失败: {e}", flush=True)

@app.get("/ipcheck")
async def root():
    return FileResponse("templates/index.html")

# Configuration
# Fix: Allow DATA_DIR override via Env to match Clash SAFE_PATHS (e.g. /root/.config/mihomo/data)
default_data_dir = os.path.join(os.getcwd(), "data")
DATA_DIR = os.getenv("DATA_DIR", default_data_dir)
os.makedirs(DATA_DIR, exist_ok=True)
print(f"LOG: Using DATA_DIR: {DATA_DIR}", flush=True)

import sys
# ... imports ...

# Global Service
from core.job_manager import JobManager

# ... imports ...

# Global Service
api_url = os.getenv("CLASH_API_URL", "http://127.0.0.1:9090")
# checker_service = CheckerService(api_url=api_url) 
# Initialized in main but logic moved
checker_service = CheckerService(api_url=api_url) 
job_manager = JobManager(checker_service)

# 检测历史记录存储(Web 界面历史列表用, 最近 50 条)
from core.history import init_history_store
history_store = init_history_store(DATA_DIR, max_items=50)
print(f"LOG: History store ready: {history_store.file_path}", flush=True)

# Force standard logging...
# ...

# Force standard logging to stdout to properly show in Docker logs
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger("Main")

def calc_md5(content) -> str:
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hashlib.md5(content).hexdigest()

def is_in_time_cache(file_path: str, max_age_seconds=None) -> bool:
    """Checks if file modification time is within max_age."""
    if max_age_seconds is None:
        max_age_seconds = config.max_age

    if not os.path.exists(file_path):
        return False
    mtime = os.path.getmtime(file_path)
    return (time.time() - mtime) < max_age_seconds

async def fetch_url_with_retry(target_url: str, timeout: int = None):
    """Helper to fetch content with specific UA."""
    headers = {"User-Agent": config.user_agent}
    timeout_val = timeout if timeout is not None else config.request_timeout
    print(f"[INFO] Downloading: {target_url} (Timeout: {timeout_val}s)", flush=True)
    resp = await asyncio.to_thread(requests.get, target_url, headers=headers, timeout=timeout_val)
    resp.raise_for_status()
    return resp.content

def is_valid_clash(data_bytes):
    try:
        d = yaml.safe_load(data_bytes)
        return isinstance(d, dict) and 'proxies' in d
    except:
        return False


def save_file_atomic(file_path: str, content: bytes):
    """
    Atomic write: writes to .tmp then renames.
    """
    tmp_path = f"{file_path}.tmp"
    try:
        with open(tmp_path, 'wb') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno()) 
        os.replace(tmp_path, file_path)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save file atomic: {e}", flush=True)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False

@app.get("/api/config")
async def get_ui_config():
    """Exposes UI configuration based on environment variables or config.yaml."""
    return {"show_advanced_settings": config.show_advanced_settings}

# ==================== 检测历史记录 API ====================

@app.get("/api/history")
async def get_history(limit: int = Query(50, description="返回条数上限")):
    """返回最近的检测历史记录列表。"""
    return {"records": history_store.list(limit=limit)}

@app.get("/api/history/{md5}")
async def get_history_detail(md5: str):
    """按 md5 返回某条历史记录的检测结果(YAML 文本)。"""
    record = history_store.get(md5)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    file_path = record.get("file_path", "")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="结果文件已过期")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {
        "md5": md5,
        "url": record.get("url", ""),
        "timestamp": record.get("timestamp", ""),
        "node_count": record.get("node_count", 0),
        "yaml": content,
    }

@app.delete("/api/history")
async def clear_history():
    """清空检测历史。"""
    history_store.clear()
    return {"status": "cleared"}

# ==================== 设置读写 API(Web 界面设置面板用) ====================

# Web 面板可选的流媒体服务(对应 MediaUnlockTest 服务名)
AVAILABLE_STREAM_PROVIDERS = [
    "Netflix", "Disney+", "Youtube Premium", "OpenAI ChatGPT", "Anthropic Claude",
    "Google Gemini", "Microsoft Copilot", "DeepSeek", "Moonshot Kimi", "Perplexity AI",
    "Spotify Registration", "Amazon Prime Video", "Hulu", "Max", "TikTok",
    "Steam", "Dazn", "Reddit", "Apple", "Bing", "iQiYi", "TVBAnywhere+",
]

@app.get("/api/settings")
async def get_settings():
    """返回 Web 可配置的设置项(数据源、流媒体开关等)。"""
    st = config.stream_test
    return {
        "source": config.source,                     # 数据源: ping0 / ippure
        "fallback": config.fallback,                 # 主源失败降级
        "request_timeout": config.request_timeout,   # IP 检测超时
        "check_url": config.check_url,               # ippure 数据源 API 地址
        "max_queue_size": config.max_queue_size,
        "max_age": config.max_age,
        "filter_risk_threshold": config.filter_risk_threshold,   # 风险节点过滤阈值
        "result_retention_days": config.result_retention_days,   # 结果保留天数
        "stream_test": {
            "enabled": st["enabled"],
            "providers": st["providers"],
            "timeout": st["timeout"],
            "conc": st["conc"],
            "node_label": st["node_label"],
        },
        "available_providers": AVAILABLE_STREAM_PROVIDERS,
    }

@app.post("/api/settings")
async def update_settings(request: Request):
    """保存 Web 设置(写回 config.yaml + 更新内存,下次检测生效)。"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="无效的 JSON")

    # 更新内存配置
    if "source" in body and body["source"] in ("ping0", "ippure", "ipapi"):
        config._config["source"] = body["source"]
    if "fallback" in body and isinstance(body["fallback"], bool):
        config._config["fallback"] = body["fallback"]
    if "request_timeout" in body and isinstance(body["request_timeout"], int):
        config._config["request_timeout"] = body["request_timeout"]
    if "check_url" in body and isinstance(body["check_url"], str) and body["check_url"].strip():
        config._config["check_url"] = body["check_url"].strip()

    # 风险节点过滤阈值(风险度超过该值的节点从输出中移除, 0 = 不过滤)
    if "filter_risk_threshold" in body:
        try:
            config._config["filter_risk_threshold"] = int(body["filter_risk_threshold"])
        except (ValueError, TypeError):
            pass

    # 结果保留天数
    if "result_retention_days" in body:
        try:
            config._config["result_retention_days"] = int(body["result_retention_days"])
        except (ValueError, TypeError):
            pass

    # 流媒体检测设置
    if "stream_test" in body and isinstance(body["stream_test"], dict):
        st = body["stream_test"]
        cur_st = config._config.get("stream_test") or {}
        if "enabled" in st and isinstance(st["enabled"], bool):
            cur_st["enabled"] = st["enabled"]
        if "providers" in st and isinstance(st["providers"], list):
            # 只保留合法服务名(避免注入任意值)
            cur_st["providers"] = [p for p in st["providers"] if p in AVAILABLE_STREAM_PROVIDERS]
        if "timeout" in st and isinstance(st["timeout"], int):
            cur_st["timeout"] = st["timeout"]
        if "conc" in st and isinstance(st["conc"], int):
            cur_st["conc"] = st["conc"]
        if "node_label" in st and isinstance(st["node_label"], bool):
            cur_st["node_label"] = st["node_label"]
        config._config["stream_test"] = cur_st

        # 立即同步到 CheckerService 的流媒体检测器(下次检测生效,无需重启)
        try:
            if checker_service.stream_tester is not None:
                checker_service.stream_tester.providers = cur_st.get("providers", [])
                checker_service.stream_tester.timeout = int(cur_st.get("timeout", 90))
                checker_service.stream_tester.conc = int(cur_st.get("conc", 20))
                checker_service.stream_node_label = bool(cur_st.get("node_label", True))
                # enabled=false 时置空检测器引用,跳过检测
                if not cur_st.get("enabled", True):
                    checker_service.stream_tester = None
                elif checker_service.stream_tester is None:
                    from stream_tester.media_unlock import MediaUnlockTester
                    checker_service.stream_tester = MediaUnlockTester(
                        binary_path=cur_st.get("binary_path", "/usr/local/bin/mediatest"),
                        providers=cur_st.get("providers", []),
                        timeout=int(cur_st.get("timeout", 90)),
                        conc=int(cur_st.get("conc", 20)),
                    )
        except Exception as e:
            print(f"[WARN] 同步流媒体配置失败: {e}", flush=True)

    # 写回 config.yaml(持久化)
    try:
        with open("config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(config._config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except Exception as e:
        print(f"[WARN] 保存 config.yaml 失败: {e}", flush=True)

    return {"status": "saved"}

@app.get("/api/status")
async def get_status_json(url: str = Query(..., description="Subscription URL")):
    """Internal JSON status API."""
    status = job_manager.get_status(url)
    q_info = job_manager.get_queue_info()
    
    # Calculate simple position info
    response = {
        "job_status": status,
        "global_queue_size": q_info["queue_size"],
        "running_job": q_info["running_job"]
    }
    
    if status["status"] == "queued":
        response["message"] = f"In Queue. Total waiting: {q_info['queue_size']}"
        
    return response

@app.get("/check")
async def ip_check(
    request: Request, 
    url: str = Query(..., description="Subscription URL"),
    max_queue_size: int = Query(None, description="Max Queue Size"),
    max_age: int = Query(None, description="Max Cache Age"),
    skip_keywords: str = Query(None, description="Skip keywords (comma separated)"),
    request_timeout: int = Query(None, description="Request timeout"),
    source: str = Query(None, description="Primary source (ping0/ippure)"),
    fallback: bool = Query(None, description="Fallback enabled"),
    filter_risk_threshold: int = Query(None, description="风险度超过该值的节点将被移除(0=不过滤)"),
    request_id: str = Query(None, description="Unique Request ID to prevent race conditions")
): 
    try:
        # 0. Optimize: Unwrap Self-Referencing URL
        # e.g. http://my-site.com/check?url=http://... -> http://...
        if "check?url=" in url:
            try:
                parsed_wrapper = urlparse(url)
                params_wrapper = parse_qs(parsed_wrapper.query)
                if 'url' in params_wrapper and params_wrapper['url'][0]:
                    unwrapped = params_wrapper['url'][0]
                    print(f"[INFO] Optimized: unwrapped recursive URL to {unwrapped}", flush=True)
                    url = unwrapped
            except Exception as e:
                print(f"[WARN] Failed to unwrap URL: {e}", flush=True)

        # Construct Options Dict
        options = {}
        if max_queue_size is not None: options["max_queue_size"] = max_queue_size
        if max_age is not None: options["max_age"] = max_age
        if skip_keywords is not None: 
            # Parse comma separated string
            options["skip_keywords"] = [k.strip() for k in skip_keywords.split(",") if k.strip()]
        if request_timeout is not None: options["request_timeout"] = request_timeout
        if source is not None: options["source"] = source
        if fallback is not None: options["fallback"] = fallback
        if filter_risk_threshold is not None: options["filter_risk_threshold"] = filter_risk_threshold

        # Local limit overrides
        current_max_queue = max_queue_size if max_queue_size is not None else config.max_queue_size
        current_max_age = max_age if max_age is not None else config.max_age

        # ... fetch & validate logic (unchanged) ...
        # 1. Download Content (Initial)
        content = await fetch_url_with_retry(url, timeout=options.get("request_timeout"))
        
        # 2. Validation & Auto-Conversion
        if not is_valid_clash(content):
             # ... auto convert logic (unchanged) ...
             # (Copy existing logic carefully or use ... if not changing)
            print("[INFO] Content is not valid Clash YAML. Attempting auto-conversion...", flush=True)
            
            try:
                # Robust URL construction using urllib
                parsed = urlparse(url)
                query = parse_qs(parsed.query)
                query.update({
                    'target': ['clash'],
                    'ver': ['meta'],
                    'flag': ['clash']
                })
                new_query = urlencode(query, doseq=True)
                new_url = urlunparse(parsed._replace(query=new_query))

                print(f"[INFO] Retrying with auto-conversion parameters...", flush=True)
                new_content = await fetch_url_with_retry(new_url, timeout=options.get("request_timeout"))
                if is_valid_clash(new_content):
                    content = new_content
                    print(f"[INFO] Auto-conversion successful.", flush=True)
                else:
                     # ... error handling (unchanged) ...
                    msg = "Invalid Clash Configuration. Expected YAML with 'proxies' key."
                    try:
                        import base64
                        decoded = base64.b64decode(content).decode('utf-8', errors='ignore')
                        if "vmess://" in decoded or "vless://" in decoded:
                            msg = "Received Base64/Raw Node List. Please use a 'Clash' target subscription link."
                    except:
                        pass
                    return PlainTextResponse(f"不支持的订阅类型： {msg}", status_code=400)
            except Exception as e:
                print(f"[WARN] Auto-conversion failed: {e}", flush=True)


        # 3. Calc MD5 (of valid content)
        md5_hash = calc_md5(content)
        file_name = f"{md5_hash}.yaml"
        file_path = os.path.join(DATA_DIR, file_name)

        # Update Map (URL -> Content Hash)
        url_hash = calc_md5(url)
        # Note: Map file doesn't track options, so multiple configs for same URL share same map/hash?
        # Actually file_name is hash of content, so content same = same file.
        # But options might differ.
        # If I change skip_keywords, output content changes.
        # So caching based on INPUT CONTENT hash is slightly risky if output depends on runtime options.
        # BUT: The input content (raw yaml) is what md5_hash is based on. 
        # The output file overwrites this file.
        # So if User A checks with keyword "A" and User B checks with keyword "B", 
        # they might overwrite each other's cache if content is identical. (Race condition on cache).
        # However, for this simplified system, we accept this risk or we'd need to salt the hash with options.
        # Let's keep it simple: Cache is based on Source Content. Re-run overwrites.
        
        map_path = os.path.join(DATA_DIR, f"{url_hash}.map")
        try:
            with open(map_path, 'w') as f:
                f.write(md5_hash)
        except Exception as e:
            print(f"[WARN] Failed to save map file: {e}", flush=True)
        
        # 4. Cache Check (Now using hash of VALID content)
        exists = os.path.exists(file_path)
        in_time_cache = is_in_time_cache(file_path, max_age_seconds=current_max_age)
        # Check if this specific URL has a job in queue or running
        is_active = job_manager.is_active_task(url)
        
        # Check if last status was cancelled (Bypass cache to allow retry)
        last_job = job_manager.jobs.get(url)
        is_cancelled = (last_job and last_job.status == "cancelled")
        
        # Check if this is a NEW request (different request_id means user wants fresh run)
        is_new_request = (request_id and last_job and last_job.request_id != request_id)

        # 5. 缓存命中：直接返回 (如果已被取消，或者是新请求ID，则不走缓存，强制重跑)
        if exists and (in_time_cache or is_active) and not is_cancelled and not is_new_request:
            print(f"[INFO] Hit cache/reuse for {file_name} (in_time_cache={in_time_cache}, active={is_active}).", flush=True)
            if not is_active:
                await job_manager.register_completed(url)
            return FileResponse(file_path, media_type="application/x-yaml", filename="checked.yaml")
        
        # 6. 先检查队列容量（在保存文件之前）
        q_info = job_manager.get_queue_info()
        total_active = q_info["queue_size"] + (1 if q_info["running_job"] else 0)
        
        if total_active >= current_max_queue:
            print(f"[WARN] Queue full ({total_active} >= {current_max_queue}).", flush=True)
            if exists:
                # 文件已存在（可能有旧的检测结果），返回已有文件
                print(f"[INFO] Returning existing file (may contain old results).", flush=True)
                return FileResponse(file_path, media_type="application/x-yaml", filename="clash.yaml", headers={"X-QC-Queue-Full": "1"})
            else:
                # 新文件，队列满无法处理，返回 503
                return PlainTextResponse(
                    "服务器繁忙，请稍后重试。当前检测队列已满。", 
                    status_code=503,
                    headers={"X-QC-Queue-Full": "1"}
                )
        
        # 7. 队列未满，保存新文件（仅首次请求）
        if not exists:
            print(f"[INFO] New task for {file_name}.", flush=True)
            # Async Atomic Save
            loop = asyncio.get_running_loop()
            if not await loop.run_in_executor(None, save_file_atomic, file_path, content):
                return PlainTextResponse("Internal Write Error", status_code=500)
        else:
            # 缓存过期，保留已有文件，直接重新检测
            print(f"[INFO] Cache stale for {file_name}, re-triggering (keeping existing file).", flush=True)
 
        # 8. Trigger Job with IP Limiting
        try:
             await job_manager.submit_job(url, file_path, user_ip=request.client.host, options=options, request_id=request_id)
        except ValueError as ve:
             # If user has a job running, 429 Too Many Requests
             return PlainTextResponse(str(ve), status_code=429)
        
        return FileResponse(file_path, media_type="application/x-yaml", filename="clash.yaml")


    except Exception as e:
        print(f"[ERROR] processing request: {type(e).__name__}: {e}", flush=True)
        return PlainTextResponse(f"Error: {str(e)}", status_code=500)

@app.post("/cancel")
async def cancel_check(url: str = Query(..., description="Subscription URL to cancel"), request_id: str = Query(None)):
    success = await job_manager.cancel_job(url, request_id)
    if success:
        return {"status": "cancelled"}
    return {"status": "not_found_or_ignored"}

@app.get("/download")
async def download_config(url: str):
    url_hash = calc_md5(url)
    map_path = os.path.join(DATA_DIR, f"{url_hash}.map")
    
    if os.path.exists(map_path):
        try:
            with open(map_path, 'r') as f:
                target_hash = f.read().strip()
            
            file_path = os.path.join(DATA_DIR, f"{target_hash}.yaml")
            if os.path.exists(file_path):
                return FileResponse(file_path, media_type="application/x-yaml", filename="clash_checked.yaml")
        except Exception as e:
            print(f"[ERROR] Map read failed: {e}", flush=True)
            pass
            
    return PlainTextResponse("File not found or expired. Please check again.", status_code=404)

@app.get("/status/stream")
async def stream_status(url: str = Query(..., description="Job URL")):
    async def event_generator():
        while True:
            # Keep alive / Heartbeat?
            if not url:
                 yield f"data: {{}}\n\n"
                 await asyncio.sleep(1)
                 continue

            status_data = job_manager.get_status(url)
            
            # Retrieve queued logs to ensure we don't miss fast updates
            job_obj = job_manager.jobs.get(url)
            logs = await job_obj.get_and_clear_logs() if job_obj else []

            if not logs:
                # No new logs, just send current state (heartbeat)
                data = json.dumps({
                    "job_status": status_data,
                    "global_queue_size": job_manager.queue.qsize()
                })
                yield f"data: {data}\n\n"
            else:
                # Send a separate event for each log message
                for msg in logs:
                    temp_status = status_data.copy()
                    temp_status["message"] = msg
                    data = json.dumps({
                        "job_status": temp_status,
                        "global_queue_size": job_manager.queue.qsize()
                    })
                    yield f"data: {data}\n\n"

            if status_data["status"] in ["completed", "error", "unknown"]:
                break

            await asyncio.sleep(1.0) # Keep 1s polling, but queue ensures no data loss

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    # Allow port configuration via env
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

