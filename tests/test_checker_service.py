# -*- coding: utf-8 -*-
"""CheckerService 纯函数单元测试: 节点名格式化、数据源顺序(不触网)。"""

from core.checker_service import CheckerService


def _cs():
    """绕过 __init__ 构造实例(避免依赖 Clash/流媒体二进制)。"""
    return CheckerService.__new__(CheckerService)


def test_strip_old_tag():
    cs = _cs()
    assert cs._strip_old_tag("HK-01 【🟡 机房|原生】") == "HK-01"
    assert cs._strip_old_tag("HK-01") == "HK-01"
    assert cs._strip_old_tag("HK-01 【旧】 【更旧】") == "HK-01"


def test_parse_score():
    assert CheckerService._parse_score("61%") == 61.0
    assert CheckerService._parse_score("?") is None
    assert CheckerService._parse_score(None) is None


def test_format_name_full():
    cs = _cs()
    res = {"pure_score": "61%", "pure_emoji": "🟡", "ip_attr": "机房",
           "ip_src": "原生", "full_string": "【🟡 机房|原生】", "error": None}
    assert cs._format_name("HK-01", res, "NF✓(us)") == "HK-01·61%·NF✓(us)【🟡 机房|原生】"


def test_format_name_no_stream():
    cs = _cs()
    res = {"pure_score": "10%", "pure_emoji": "🟢", "ip_attr": "住宅",
           "ip_src": "原生", "full_string": "【🟢 住宅|原生】", "error": None}
    assert cs._format_name("HK-01", res, "") == "HK-01·10%【🟢 住宅|原生】"


def test_format_name_strips_old_tag():
    cs = _cs()
    res = {"pure_score": "10%", "pure_emoji": "🟢", "ip_attr": "住宅",
           "ip_src": "原生", "full_string": "【🟢 住宅|原生】", "error": None}
    assert cs._format_name("HK-01 【旧标注】", res, "") == "HK-01·10%【🟢 住宅|原生】"


def test_format_name_error():
    cs = _cs()
    res = {"pure_score": "?", "error": "boom"}
    assert cs._format_name("HK-01", res, "") == "HK-01 【❌ 失败】"


# ---------- 数据源顺序(FALLBACK_POOL 收敛为可用源) ----------

def test_ipapi_no_fallback():
    assert CheckerService._build_source_order("ipapi", False, {"ipapi", "ping0", "ippure"}) == ["ipapi"]


def test_ipapi_fallback_keeps_only_available():
    # 自动降级只回落到可用池,不再白等已被拦截/失效的 ping0/ippure
    assert CheckerService._build_source_order("ipapi", True, {"ipapi", "ping0", "ippure"}) == ["ipapi"]


def test_ping0_primary_with_fallback():
    # 手动选 ping0 为主源时,可兜底到 ipapi
    assert CheckerService._build_source_order("ping0", True, {"ipapi", "ping0", "ippure"}) == ["ping0", "ipapi"]


def test_ping0_primary_no_fallback():
    assert CheckerService._build_source_order("ping0", False, {"ipapi", "ping0", "ippure"}) == ["ping0"]
