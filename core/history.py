# -*- coding: utf-8 -*-
"""检测历史记录存储

把每次检测任务的结果留存到 DATA_DIR/history.json,
支持按时间倒序查看最近 N 条记录,用于 Web 界面回看历史结果。

记录结构:
{
    "md5":      订阅内容 MD5(唯一标识,即结果文件名),
    "url":      订阅链接,
    "timestamp": 完成时间 ISO 字符串,
    "file_path": 结果 YAML 文件绝对路径,
    "node_count": 节点数量
}
"""

import json
import logging
import os
import threading
import time
from typing import Dict, List, Optional

logger = logging.getLogger("HistoryStore")

# 最多保留的历史条数
DEFAULT_MAX_ITEMS = 50


class HistoryStore:
    """基于 JSON 文件的检测历史记录存储(线程安全)。"""

    def __init__(self, data_dir: str, max_items: int = DEFAULT_MAX_ITEMS):
        self.data_dir = data_dir
        self.max_items = max_items
        self.file_path = os.path.join(data_dir, "history.json")
        self._lock = threading.Lock()
        os.makedirs(data_dir, exist_ok=True)
        self._records: List[Dict] = self._load()

    def _load(self) -> List[Dict]:
        """从磁盘加载历史记录(倒序: 最新在前)。"""
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
        except Exception as e:
            logger.error("加载历史记录失败: %s", e)
        return []

    def _save(self) -> None:
        """原子写入磁盘。"""
        tmp = f"{self.file_path}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._records, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.file_path)
        except Exception as e:
            logger.error("保存历史记录失败: %s", e)

    def add(self, md5: str, url: str, file_path: str, node_count: int = 0) -> None:
        """新增一条历史记录(同 md5 更新,其余去重)。"""
        with self._lock:
            record = {
                "md5": md5,
                "url": url,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "file_path": file_path,
                "node_count": node_count,
            }
            # 同 md5 视为同一条,更新;否则插到最前
            self._records = [r for r in self._records if r.get("md5") != md5]
            self._records.insert(0, record)
            # 只保留最近 max_items 条
            if len(self._records) > self.max_items:
                self._records = self._records[: self.max_items]
            self._save()

    def list(self, limit: int = DEFAULT_MAX_ITEMS) -> List[Dict]:
        """返回最近 limit 条历史(不含 file_path 绝对路径,避免泄露服务器路径)。"""
        with self._lock:
            result = []
            for r in self._records[:limit]:
                item = {
                    "md5": r.get("md5", ""),
                    "url": r.get("url", ""),
                    "timestamp": r.get("timestamp", ""),
                    "node_count": r.get("node_count", 0),
                }
                result.append(item)
            return result

    def get(self, md5: str) -> Optional[Dict]:
        """按 md5 查询单条记录。"""
        with self._lock:
            for r in self._records:
                if r.get("md5") == md5:
                    return dict(r)
            return None

    def clear(self) -> None:
        """清空历史。"""
        with self._lock:
            self._records = []
            self._save()

    def prune_missing_files(self) -> int:
        """移除结果文件已不存在的历史条目,返回移除数量。"""
        with self._lock:
            before = len(self._records)
            self._records = [r for r in self._records if os.path.exists(r.get("file_path", ""))]
            if len(self._records) != before:
                self._save()
            return before - len(self._records)


# 全局单例(在 main.py 初始化)
history_store: Optional[HistoryStore] = None


def init_history_store(data_dir: str, max_items: int = DEFAULT_MAX_ITEMS) -> HistoryStore:
    """初始化全局历史存储单例。"""
    global history_store
    history_store = HistoryStore(data_dir, max_items)
    return history_store


def get_history_store() -> HistoryStore:
    """获取全局历史存储单例。"""
    assert history_store is not None, "HistoryStore 未初始化"
    return history_store
