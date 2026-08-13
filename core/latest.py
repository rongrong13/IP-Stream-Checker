# -*- coding: utf-8 -*-
"""最新检测结果固定文件 + 历史快照管理。

OpenClash 等客户端订阅固定的 http://IP:8000/latest 即可: 每次检测完成后
自动更新该文件(名字不变),更新前把旧结果备份为历史快照(保留最近 N 份),
可在 Web 面板查看/复制历史版本。

健壮性设计:
- 原子写入(tmp + os.replace),避免读到写一半的文件
- 快照保留份数超限自动清理最旧
- 所有文件操作独立 try/except,失败不中断主流程(由调用方兜底)
"""

import os
import shutil
import time

LATEST_FILENAME = "latest.yaml"
HISTORY_DIRNAME = "latest_history"
DEFAULT_MAX_SNAPSHOTS = 10


def _snapshot_name(ts: float) -> str:
    """快照文件名: latest-YYYYmmdd-HHMMSS.yaml"""
    return "latest-" + time.strftime("%Y%m%d-%H%M%S", time.localtime(ts)) + ".yaml"


def _is_snapshot_name(filename: str) -> bool:
    return filename.startswith("latest-") and filename.endswith(".yaml")


def prune_snapshots(history_dir: str, max_snapshots: int) -> int:
    """保留最近 max_snapshots 份快照,删除更旧的,返回删除数量。"""
    if not os.path.isdir(history_dir) or max_snapshots <= 0:
        return 0
    snapshots = sorted(
        (f for f in os.listdir(history_dir) if _is_snapshot_name(f)),
        key=lambda f: os.path.getmtime(os.path.join(history_dir, f)),
        reverse=True,
    )
    removed = 0
    for old in snapshots[max_snapshots:]:
        try:
            os.remove(os.path.join(history_dir, old))
            removed += 1
        except OSError:
            pass
    return removed


def update_latest(data_dir: str, result_file: str, max_snapshots: int = DEFAULT_MAX_SNAPSHOTS) -> str:
    """把新的检测结果写为 latest.yaml,并把旧版本备份为历史快照。

    Args:
        data_dir:     数据目录(DATA_DIR)
        result_file:  本次检测结果的 YAML 文件绝对路径
        max_snapshots: 保留的历史快照份数

    Returns:
        写入的 latest.yaml 绝对路径。任何失败抛出异常(调用方 try/except 兜底)。
    """
    latest_path = os.path.join(data_dir, LATEST_FILENAME)
    history_dir = os.path.join(data_dir, HISTORY_DIRNAME)

    # 1. 备份当前 latest(若有)为历史快照
    if os.path.exists(latest_path):
        os.makedirs(history_dir, exist_ok=True)
        snap = os.path.join(history_dir, _snapshot_name(time.time()))
        n = 1
        # 同秒多次更新时追加序号,避免覆盖
        while os.path.exists(snap):
            snap = os.path.join(history_dir, _snapshot_name(time.time() + n))
            n += 1
        shutil.copy2(latest_path, snap)

    # 2. 原子写入新结果
    tmp = latest_path + ".tmp"
    with open(tmp, "wb") as f:
        with open(result_file, "rb") as src:
            shutil.copyfileobj(src, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, latest_path)

    # 3. 清理超出保留份数的快照
    prune_snapshots(history_dir, max_snapshots)
    return latest_path


def list_snapshots(data_dir: str, max_items: int = 50) -> list:
    """列出历史快照(新→旧),返回 [{filename, timestamp, size}]。"""
    history_dir = os.path.join(data_dir, HISTORY_DIRNAME)
    if not os.path.isdir(history_dir):
        return []
    items = []
    for f in os.listdir(history_dir):
        if not _is_snapshot_name(f):
            continue
        fpath = os.path.join(history_dir, f)
        try:
            st = os.stat(fpath)
        except OSError:
            continue
        items.append({
            "filename": f,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
            "size": st.st_size,
        })
    # 文件名含时间戳,按文件名倒序 = 新→旧
    items.sort(key=lambda i: i["filename"], reverse=True)
    return items[:max_items]


def is_valid_snapshot_filename(filename: str) -> bool:
    """文件名白名单校验(防路径穿越): 仅允许 latest-*.yaml,且不含路径分隔符。"""
    return (_is_snapshot_name(filename)
            and "/" not in filename and "\\" not in filename
            and ".." not in filename)
