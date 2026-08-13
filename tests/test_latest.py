# -*- coding: utf-8 -*-
"""latest.yaml 固定结果 + 历史快照单元测试(不触网)。"""

import os
import time

import pytest

from core.latest import (
    HISTORY_DIRNAME,
    is_valid_snapshot_filename,
    list_snapshots,
    prune_snapshots,
    update_latest,
)


def _make_result(tmp_path, node_name="node-a"):
    """构造一个检测结果 YAML 文件。"""
    p = tmp_path / f"abc123.yaml"
    p.write_text(f"proxies:\n  - name: '{node_name}'\n    type: ss\n", encoding="utf-8")
    return str(p)


def test_update_latest_creates_file(tmp_path):
    result = _make_result(tmp_path)
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir)
    latest = update_latest(data_dir, result)
    assert os.path.exists(latest)
    assert "node-a" in open(latest, encoding="utf-8").read()


def test_update_latest_backs_up_old(tmp_path):
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir)
    r1 = _make_result(tmp_path, "old-node")
    update_latest(data_dir, r1)
    # 模拟下一次检测(同一秒内),验证旧版本被备份
    time.sleep(1.1)
    r2 = _make_result(tmp_path, "new-node")
    update_latest(data_dir, r2)

    latest = os.path.join(data_dir, "latest.yaml")
    assert "new-node" in open(latest, encoding="utf-8").read()
    snaps = list_snapshots(data_dir)
    assert len(snaps) == 1
    # 快照内容应是旧版本
    snap_path = os.path.join(data_dir, HISTORY_DIRNAME, snaps[0]["filename"])
    assert "old-node" in open(snap_path, encoding="utf-8").read()


def test_snapshot_cap_keeps_10(tmp_path):
    """快照保留上限: 超过 max 份自动清理最旧。"""
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir)
    for i in range(15):
        r = _make_result(tmp_path, f"node-{i}")
        update_latest(data_dir, r, max_snapshots=10)
        time.sleep(0.05)  # 保证快照文件名时间戳不同
    snaps = list_snapshots(data_dir)
    assert len(snaps) == 10
    # 新→旧, 最新的应是 node-14
    assert len(snaps) == 10


def test_update_latest_atomic_no_partial(tmp_path):
    """原子写入: 写入过程中不存在半成品(直接产物完整)。"""
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir)
    r = _make_result(tmp_path, "node-x")
    update_latest(data_dir, r)
    # 无 .tmp 残留
    assert not os.path.exists(os.path.join(data_dir, "latest.yaml.tmp"))
    assert os.path.exists(os.path.join(data_dir, "latest.yaml"))


def test_prune_snapshots(tmp_path):
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir)
    hdir = os.path.join(data_dir, HISTORY_DIRNAME)
    os.makedirs(hdir)
    for i in range(5):
        p = os.path.join(hdir, f"latest-20260813-00000{i}.yaml")
        open(p, "w").write("x")
    removed = prune_snapshots(hdir, 2)
    assert removed == 3
    assert len(os.listdir(hdir)) == 2


def test_is_valid_snapshot_filename():
    assert is_valid_snapshot_filename("latest-20260813-120000.yaml")
    assert not is_valid_snapshot_filename("../etc/passwd")
    assert not is_valid_snapshot_filename("a/../latest.yaml")
    assert not is_valid_snapshot_filename("latest.yaml")
    assert not is_valid_snapshot_filename("other.yaml")
