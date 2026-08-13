# -*- coding: utf-8 -*-
"""ipapi 数据源评分与属性判定单元测试(纯函数,不触网)。"""

from core.sources.ipapi import IpApiSource


def _score(hosting=False, proxy=False, mobile=False, org="", isp=""):
    return IpApiSource()._score_risk({
        "hosting": hosting, "proxy": proxy, "mobile": mobile,
        "org": org, "isp": isp,
    })


def test_clean_residential_zero():
    # 家宽 ISP、无代理无机房 -> 0
    assert _score(org="AS4134 China Telecom", isp="China Telecom") == 0


def test_hosting_only_45():
    assert _score(hosting=True, org="AS16509 Amazon.com, Inc.") == 45


def test_proxy_only_35():
    # 家宽 ISP 上的代理: 代理 +35,住宅关键词 -15 -> 20
    assert _score(proxy=True, org="AS4134 China Telecom", isp="China Telecom") == 20


def test_proxy_on_cloud_ip_50():
    # 云 IP 上的代理: 代理 35 + 云 15
    assert _score(proxy=True, org="AS13335 Cloudflare, Inc.") == 50


def test_cloud_asn_without_hosting_flag_15():
    # 云 ASN 命中但 hosting 标记为 False -> +15
    assert _score(org="AS16509 Amazon.com, Inc.") == 15


def test_mobile_minus_10():
    assert _score(mobile=True, org="AS9808 China Mobile", isp="China Mobile") == 0


def test_hosting_plus_proxy_80():
    assert _score(hosting=True, proxy=True, org="AS16509 Amazon.com, Inc.") == 80


def test_residential_overrides_hosting_flag():
    # 家宽 ISP 覆盖 hosting 标记(降低误判)
    assert _score(hosting=True, org="AS4134 China Telecom", isp="China Telecom") == 0


def test_cloud_detection():
    assert IpApiSource._is_cloud_ip("AS16509 Amazon.com, Inc.") is True
    assert IpApiSource._is_cloud_ip("AS4134 China Telecom") is False


def test_residential_detection():
    assert IpApiSource._is_residential_org("China Telecom Guangdong") is True
    assert IpApiSource._is_residential_org("Amazon.com, Inc.") is False
