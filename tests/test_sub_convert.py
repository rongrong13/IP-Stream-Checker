# -*- coding: utf-8 -*-
"""订阅多格式解析单元测试: 纯 URI 行 / Base64 → Clash YAML(不触网)。"""

import base64
import yaml as _yaml

from core.sub_convert import convert_to_clash_yaml


def _apply_convert(content_bytes):
    """转出 Clash YAML, 并解析为 dict 供断言。"""
    yaml_bytes = convert_to_clash_yaml(content_bytes)
    assert yaml_bytes is not None
    return _yaml.safe_load(yaml_bytes)


def test_clean_urls_parse():
    """常见的机场订阅格式: 服务器地址+端口+密码+名字。"""
    uri = "trojan://pass@1.2.3.4:443?security=tls&sni=node.example.com#HK-01"
    doc = _apply_convert(uri.encode())
    assert len(doc["proxies"]) == 1
    p = doc["proxies"][0]
    assert p["type"] == "trojan"
    assert p["server"] == "1.2.3.4"
    assert p["port"] == 443
    assert p["name"] == "HK-01"
    assert p["sni"] == "node.example.com"


def test_multiline_uris():
    """纯 URI 文本, 每行一个节点。"""
    text = "\n".join([
        "vless://uuid@9.8.7.6:443?security=reality&sni=real.example.com&type=tcp#JP-01",
        "vmess://" + base64.b64encode(
            b'{"ps":"US-01","add":"5.6.7.8","port":"443","id":"xxxx","aid":"0","net":"ws",'
            b'"tls":"tls","host":"cdn.example.com","path":"/ws"}').decode(),
    ])
    doc = _apply_convert(text.encode())
    names = [p["name"] for p in doc["proxies"]]
    assert "JP-01" in names and "US-01" in names


def test_base64_subscription():
    """Base64 编码的纯 URI 订阅(最常见通用格式)。"""
    raw = "\n".join(["ss://" + base64.b64encode(b"aes-128-gcm:pwd@1.2.3.4:8388").decode() + "#SG-01"])
    b64 = base64.b64encode(raw.encode()).decode()
    doc = _apply_convert(b64.encode())
    assert len(doc["proxies"]) == 1
    assert doc["proxies"][0]["name"] == "SG-01"


def test_yaml_passthrough_not_handled():
    """纯 Clash YAML 不属于本模块职责(由 main 的 is_valid_clash 处理), 此处应返回 None。"""
    yaml_bytes = b"proxies:\n  - name: a\n    type: ss\n    server: 1.1.1.1\n    port: 80\n    cipher: aes\n    password: x\n"
    # 该内容既非 URI 行也无 URI, 应无法转换
    assert convert_to_clash_yaml(yaml_bytes) is None


def test_garbage_returns_none():
    assert convert_to_clash_yaml(b"not a subscription among anything") is None


def test_bad_node_skipped():
    """格式损坏的节点被跳过, 不影响其它正常节点。"""
    text = "\n".join([
        "not-a-uri-here",
        "ss://" + base64.b64encode(b"aes-256-gcm:passwd@10.0.0.1:9000").decode() + "#OK-node",
        "vmess://not-base64"
    ])
    doc = _apply_convert(text.encode())
    assert [p["name"] for p in doc["proxies"]] == ["OK-node"]


def test_hysteria2_and_tuic():
    text = "\n".join([
        "hysteria2://pass@1.1.1.1:8443?insecure=1&sni=hy.example.com#HY-node",
        "tuic://uuid:pp@3.3.3.3:443?sni=tc.example.com#TU-node",
    ])
    doc = _apply_convert(text.encode())
    assert [p["type"] for p in doc["proxies"]] == ["hysteria2", "tuic"]


def test_proxy_groups_and_rules_present():
    """输出包含 proxy-groups 与 rules, 检测管线可直接加载。"""
    uri = "ss://" + base64.b64encode(b"aes:a@1.2.3.4:5").decode() + "#A"
    doc = _apply_convert(uri.encode())
    assert "proxy-groups" in doc and "rules" in doc
