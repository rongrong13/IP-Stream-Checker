# -*- coding: utf-8 -*-
"""订阅多格式本地解析: 纯 URI 行 / Base64 订阅 → Clash YAML。

背景: 本地 IP-Stream-Checker 之前只认 Clash YAML(含 'proxies' key),
纯 URI 文本(如 vless:// 每行一个)或通用 Base64 订阅会判无效并依赖服务端
target=clash 转换(订阅站不支持时直接报错)。本模块在本地完成解析,
覆盖常见协议: vmess / vless / ss / trojan / hysteria2 / tuic。

健壮性设计:
- 所有解析函数独立容错,单条节点解析失败跳过,不中断整体
- Base64 解码失败/内容不可读时判定为"非 Base64 订阅",交给调用方走其它路径
- 转换失败返回 None,由调用方决定降级或报错
"""

import base64
import binascii
import json
import re
import urllib.parse
import yaml

# 支持的代理协议 scheme
URI_SCHEMES = ("vmess://", "vless://", "ss://", "trojan://", "hysteria2://", "tuic://")

# URI 行提取: 允许行首带前缀(如 # 注释后、列表项 "- "、JSON 转义 \n 等)
_LINE_RE = re.compile(r"(?:^|[\s\"',\[-])((?:vmess|vless|ss|trojan|hysteria2|tuic)://[^\s\"',\]]+)")


# ==================== Base64 检测/解码 ====================

def _looks_base64(data: bytes) -> bool:
    """启发式判断是否为 Base64 编码的订阅内容。"""
    if not data:
        return False
    text = data.strip()
    if len(text) < 16:
        return False
    # 去空白后应全由 base64 字符组成
    compact = re.sub(rb"\s+", b"", text)
    if not compact:
        return False
    if not re.fullmatch(rb"[A-Za-z0-9+/=]+", compact):
        return False
    return len(compact) % 4 in (0, 2, 3)  # 合法 base64 长度特征


def decode_base64_subscription(data: bytes):
    """尝试把 Base64 订阅解码为 UTF-8 文本;失败返回 None。"""
    if not _looks_base64(data):
        return None
    try:
        decoded = base64.b64decode(data, validate=True)
        return decoded.decode("utf-8", errors="ignore")
    except (binascii.Error, ValueError):
        return None


# ==================== 协议解析(均返回 Clash proxy dict 或 None) ====================

def _clean_name(raw: str, fallback: str, used_names: set) -> str:
    """规范化节点名: 解码 + 去空白 + 保证唯一(重复时加序号)。"""
    name = urllib.parse.unquote(raw or "").strip()
    if not name:
        name = fallback
    name = re.sub(r"[\x00-\x1f]+", "", name)[:120]
    if not name:
        name = fallback
    base, n = name, 1
    while name in used_names:
        n += 1
        name = f"{base}-{n}"
    used_names.add(name)
    return name


def _parse_ss(raw: str) -> dict:
    """ss:// 支持旧式 base64(method:pass@host:port) 与 SIP002 明文/plugin 形式。"""
    body = raw[len("ss://"):]
    # 去掉 fragment 名称
    frag = None
    if "#" in body:
        body, frag = body.split("#", 1)
    # 形如 base64(method:pass@host:port)?plugin=...
    query = ""
    if "?" in body:
        body, query = body.split("?", 1)
    params = urllib.parse.parse_qs(query)
    # 先判断原始串是否含 "@": 不含则为整串等幂的 base64(userinfo=whole#host), 需整串解码
    if "@" in body:
        userinfo, _, hostport = body.rpartition("@")
    else:
        try:
            decoded = base64.b64decode(body).decode("utf-8", errors="ignore")
        except Exception:
            return None
        if "@" not in decoded:
            return None
        userinfo, _, hostport = decoded.rpartition("@")
    host, _, port = hostport.rpartition(":")
    if not host or not port.isdigit():
        return None
    # userinfo 形如 method:password(可能带 base64 method)
    if ":" in userinfo:
        method, password = userinfo.split(":", 1)
        method = urllib.parse.unquote(method)
        # 部分订阅把 method:pass 整体 base64 过
        try:
            if re.fullmatch(r"[A-Za-z0-9+/=]{4,}", method):
                method = base64.b64decode(method).decode("utf-8", errors="ignore")
        except Exception:
            pass
    else:
        return None
    proxy = {
        "name": frag or f"ss-{host}:{port}",
        "type": "ss",
        "server": host,
        "port": int(port),
        "cipher": method,
        "password": urllib.parse.unquote(password),
    }
    # SIP002 plugin(v2ray-plugin 常见)
    plugin_val = params.get("plugin", [None])[0]
    if plugin_val:
        plugin_val = urllib.parse.unquote(plugin_val)
        if plugin_val.startswith("obfs-"):
            proxy["plugin"] = "obfs"
            opts = dict(p.split("=", 1) for p in plugin_val.split(";")[1:] if "=" in p)
            proxy["plugin-opts"] = {"mode": opts.get("mode", "http"), "host": opts.get("host", "")}
        elif plugin_val.startswith("v2ray-plugin"):
            opts = dict(p.split("=", 1) for p in plugin_val.split(";")[1:] if "=" in p)
            mode = "websocket" if opts.get("mode", "websocket") == "websocket" else "quic"
            proxy["plugin"] = "v2ray-plugin"
            po = {"mode": mode}
            if opts.get("host"):
                po["host"] = opts["host"]
            if opts.get("path"):
                po["path"] = opts["path"]
            if opts.get("tls") == "true":
                po["tls"] = True
            proxy["plugin-opts"] = po
    return proxy


def _parse_vmess(raw: str) -> dict:
    """vmess://base64(JSON), 字段: ps/add/port/id/aid/net/type/tls/host/path/sni/flow。"""
    body = raw[len("vmess://"):]
    try:
        decoded = base64.b64decode(body).decode("utf-8", errors="ignore")
        info = json.loads(decoded)
    except Exception:
        return None
    host = str(info.get("add", "")).strip()
    port = info.get("port")
    if not host or not str(port).isdigit():
        return None
    network = info.get("net") or "tcp"
    tls = info.get("tls") or "none"
    proxy = {
        "name": str(info.get("ps", "") or f"vmess-{host}:{port}"),
        "type": "vmess",
        "server": host,
        "port": int(port),
        "uuid": str(info.get("id", "")),
        "alterId": int(info.get("aid", 0) or 0),
        "cipher": info.get("scy", "auto") or "auto",
        "tls": tls != "none",
    }
    if network != "tcp":
        proxy["network"] = network
        if network == "ws":
            proxy["ws-opts"] = {
                "path": info.get("path") or "/",
                "headers": {"Host": info.get("host", "")} if info.get("host") else {},
            }
        elif network in ("grpc", "h2"):
            proxy["servername"] = info.get("host") or ""
            if info.get("path"):
                proxy[network + "-opts"] = {"grpc-service-name": info["path"]}
    if tls == "tls" and info.get("sni"):
        proxy["servername"] = info["sni"]
    elif not proxy.get("servername") and tls != "none":
        proxy["servername"] = info.get("host") or host
    return proxy


def _parse_uri_generic(raw: str, scheme: str, proxy_type: str) -> dict:
    """vless/trojan/hysteria2/tuic 通用解析: scheme://userinfo@host:port?query#name"""
    body = raw[len(scheme):]
    frag = ""
    if "#" in body:
        body, frag = body.split("#", 1)
    query = ""
    if "?" in body:
        body, query = body.split("?", 1)
    params = urllib.parse.parse_qs(query)
    userinfo, _, hostport = body.rpartition("@")
    if not hostport:
        return None
    host, _, port = hostport.rpartition(":")
    if not host or not port.isdigit():
        return None

    proxy = {"name": frag or f"{proxy_type}-{host}:{port}",
             "type": proxy_type, "server": host, "port": int(port)}

    if proxy_type == "vless":
        proxy["uuid"] = userinfo
        proxy["cipher"] = "auto"
        network = params.get("type", ["tcp"])[0]
        security = params.get("security", [""])[0]
        if security in ("tls", "reality"):
            proxy["tls"] = True
            proxy["servername"] = params.get("sni", [params.get("fp", [host])[0]])[0] or host
            if security == "reality":
                proxy["reality-opts"] = {
                    "public-key": params.get("pbk", [""])[0],
                    "short-id": params.get("sid", [""])[0],
                }
        flow = params.get("flow", [""])[0]
        if flow:
            proxy["flow"] = flow
        if network != "tcp":
            proxy["network"] = network
            if network == "ws":
                proxy["ws-opts"] = {"path": params.get("path", ["/"])[0],
                                    "headers": {"Host": params.get("host", [""])[0]}}
            elif network == "grpc":
                proxy["grpc-opts"] = {"grpc-service-name": params.get("serviceName", [""])[0]}
        return proxy

    if proxy_type == "trojan":
        proxy["password"] = urllib.parse.unquote(userinfo)
        if params.get("sni", [""])[0]:
            proxy["sni"] = params["sni"][0]
        if params.get("allowInsecure", ["0"])[0] in ("1", "true"):
            proxy["skip-cert-verify"] = True
        return proxy

    if proxy_type == "hysteria2":
        proxy["password"] = urllib.parse.unquote(userinfo)
        if params.get("sni", [""])[0]:
            proxy["sni"] = params["sni"][0]
        if params.get("insecure", ["0"])[0] in ("1", "true"):
            proxy["skip-cert-verify"] = True
        obfs = params.get("obfs", [""])[0]
        if obfs:
            proxy["obfs"] = obfs
            if params.get("obfs-password", [""])[0]:
                proxy["obfs-password"] = params["obfs-password"][0]
        return proxy

    if proxy_type == "tuic":
        # userinfo 形如 uuid:password(密码可选)
        if ":" in userinfo:
            proxy["uuid"], proxy["password"] = userinfo.split(":", 1)
        else:
            proxy["uuid"] = userinfo
        if params.get("sni", [""])[0]:
            proxy["sni"] = params["sni"][0]
        if params.get("congestion_control", [""])[0]:
            proxy["congestion-controller"] = params["congestion_control"][0]
        alpn = params.get("alpn", [""])[0]
        if alpn:
            proxy["alpn"] = [a.strip() for a in alpn.split(",") if a.strip()]
        if params.get("allow_insecure", ["0"])[0] in ("1", "true"):
            proxy["skip-cert-verify"] = True
        return proxy

    return None


# ==================== 入口 ====================

def parse_uri_line(line: str, used_names: set):
    """解析单个 URI 行为 Clash proxy dict;不支持/失败返回 None。"""
    line = line.strip()
    if not line:
        return None
    for scheme in URI_SCHEMES:
        if line.startswith(scheme):
            try:
                if scheme == "ss://":
                    p = _parse_ss(line)
                elif scheme == "vmess://":
                    p = _parse_vmess(line)
                elif scheme == "vless://":
                    p = _parse_uri_generic(line, "vless://", "vless")
                elif scheme == "trojan://":
                    p = _parse_uri_generic(line, "trojan://", "trojan")
                elif scheme == "hysteria2://":
                    p = _parse_uri_generic(line, "hysteria2://", "hysteria2")
                elif scheme == "tuic://":
                    p = _parse_uri_generic(line, "tuic://", "tuic")
                else:
                    p = None
            except Exception:
                p = None
            if p and p.get("name"):
                p["name"] = _clean_name(p["name"], f"{p['type']}-{p.get('server', '?')}", used_names)
            return p
    return None


def convert_to_clash_yaml(content) -> bytes:
    """把纯 URI 行 / Base64 订阅转换为 Clash YAML;无法识别返回 None。

    Args:
        content: 订阅原始 bytes

    Returns:
        Clash YAML bytes(proxies + proxy-groups + rules), 或 None
    """
    if isinstance(content, str):
        content = content.encode("utf-8")

    text = decode_base64_subscription(content)
    if text is None:
        # 非 Base64: 直接当文本处理(可能是纯 URI 行)
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            return None

    # 逐行收集 URI(容忍每行一个、JSON 字符串、列表项等形态)
    used_names = set()
    proxies = []
    for m in _LINE_RE.finditer(text):
        p = parse_uri_line(m.group(1), used_names)
        if p:
            proxies.append(p)

    if not proxies:
        return None

    # 组装标准 Clash 结构(global 模式 + 简单组, 检测管线可直接加载)
    group_names = [p["name"] for p in proxies]
    doc = {
        "proxies": proxies,
        "proxy-groups": [
            {"name": "节点选择", "type": "select", "proxies": ["DIRECT"] + group_names},
        ],
        "rules": ["MATCH,DIRECT"],
    }
    return yaml.safe_dump(doc, allow_unicode=True, default_flow_style=False, sort_keys=False).encode("utf-8")
