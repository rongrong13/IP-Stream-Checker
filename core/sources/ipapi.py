# -*- coding: utf-8 -*-
"""IP-API 数据源(免费启发式 IP 风险检测)

背景: ping0.cc / scamalytics 等免费风险检测站被 Cloudflare Turnstile 验证码拦截,
自动化请求拿不到真实数据; ippure 官方 API 与常用镜像也已失效。
本数据源改用 ip-api.com(免费、无反爬、支持代理)实时获取节点出口 IP 及属性,
再结合启发式规则计算 0-100 的风险度。

数据来源(均走节点代理,检测的是节点出口 IP 的真实属性):
- ip-api.com/json: 出口 IP(query)、机房(hosting)、代理(proxy)、移动网络(mobile)、ISP/ASN(org)
启发式风险评分:
    hosting(机房)               +45
    proxy(代理/VPN)             +35
    ISP 匹配云厂商/机房关键词    +15
    mobile(移动网络,多为住宅)    -10
    最终 0-100 取整
"""

import asyncio
import logging
import re
from typing import Dict, Any
from curl_cffi.requests import AsyncSession
from .base import BaseSource
from ..config import config

logger = logging.getLogger("IpApiSource")

# 常见云厂商 / VPS 商 ASN 号(命中即判定为机房类 IP)
CLOUD_ASNS = {
    "13335", "16509", "14618", "15169", "396982", "8075", "14061", "16276",
    "63949", "20473", "24940", "213230", "51167", "44684", "21859", "9009",
    "45102", "37963", "45090", "139341", "13432",
    # 扩充: 更多常见云厂商/机房 ASN
    "54113",  # Fastly
    "20940",  # Akamai
    "16625",  # Akamai
    "26496",  # AS-26496-GO-DADDY-COM-LLC (GoDaddy)
    "16509",  # Amazon (已有)
    "22822",  # Limelight
    "3333",   # XS4ALL (旧)
    "32244",  # Liquid Web
    "46606",  # Unified Layer
    "7018",   # AT&T (IDC 段)
    "36351",  # SoftLayer
    "32097",  # WholeSale Internet
    "8100",   # QuadraNet
    "53850",  # Zappie Host
    "57374",  # Dedicated Server
    "152194",  # 阿里云(国际)
    "45102",  # 阿里云(已有)
    "132203",  # 腾讯云
    "45090",  # 腾讯云(已有)
    "55990",  # 华为云
    "136907",  # 华为云
    "136958",  # 华为云
    "58519",  # 京东云
    "38895",  # 金山云
    "138692",  # 百度智能云
    "55967",  # 百度智能云
}

# ISP / 组织名中的机房关键词(中英文)
CLOUD_KEYWORDS = (
    "cloud", "hosting", "data center", "datacenter", "vps", "idc", "server",
    "机房", "数据中心", "阿里云", "腾讯云", "华为云", "aws", "azure", "gcp",
    "digitalocean", "linode", "vultr", "ovh", "hetzner", "contabo",
    # 扩充: 补充常见机房/IDC 品牌关键词
    "colocrossing", "kamatera", "serverius", "ionos", "hostwinds", "namecheap",
    "hostgator", "godaddy", "bluehost", "dreamhost", "liquidweb", "cogent",
    "zayo", "cologix", "equinix", "fiberhub", "leaseweb", "porkbun",
    "sakura", "conoha", "aws amazon", "amazon.com", "microsoft", "google llc",
)

# 明显的住宅宽带 ISP 关键词(降低机房误判)
RESIDENTIAL_KEYWORDS = (
    "china telecom", "china unicom", "china mobile", "chunghwa telecom",
    "vodafone", "o2", "telefonica", "deutsche telekom", "orange",
    "comcast", "verizon", "at&t", "time warner", "charter", "cox",
    "sk telecom", "kt corp", "lg u+", "nokia", "中国电信", "中国联通", "中国移动",
    "台湾大哥大", "远传电信", "中华电信", "香港电讯", "和记电讯",
)


class IpApiSource(BaseSource):
    @property
    def name(self) -> str:
        return "ipapi"

    def _score_risk(self, data: Dict[str, Any]) -> int:
        """根据 ip-api 返回的字段计算启发式风险度(0-100)。

        规则(与旧逻辑兼容,细节增强):
            hosting(机房标记)            +45
            proxy(代理/VPN 标记)         +35
            ISP 匹配云厂商/机房关键词    +15
            命中明显住宅宽带 ISP         -15(防止把家宽 ISP 误判为机房)
            mobile(移动网络,多为住宅)    -10
        """
        hosting = bool(data.get("hosting"))
        proxy = bool(data.get("proxy"))
        mobile = bool(data.get("mobile"))
        org = str(data.get("org", "") or "") + " " + str(data.get("isp", "") or "")
        org_lower = org.lower()

        # 云厂商 ASN 匹配(如 "AS16509 Amazon.com, Inc.")
        is_cloud = False
        m = re.search(r"AS(\d+)", org, re.IGNORECASE)
        if m and m.group(1) in CLOUD_ASNS:
            is_cloud = True
        if any(kw in org_lower for kw in CLOUD_KEYWORDS):
            is_cloud = True
        # 明显住宅宽带 ISP 覆盖机房关键词判定(降低误判)
        is_residential = any(kw in org_lower for kw in RESIDENTIAL_KEYWORDS)
        if is_residential:
            is_cloud = False

        score = 0
        if hosting and not is_residential:
            score += 45
        if proxy:
            score += 35
        if is_cloud and not hosting:
            score += 15
        if mobile:
            score -= 10
        if is_residential:
            score = max(score - 15, 0)
        return max(0, min(100, score))

    async def check(self, proxy_url: str, timeout: int = None) -> Dict[str, Any]:
        url = "http://ip-api.com/json/?fields=status,message,query,country,countryCode,regionName,city,isp,org,proxy,hosting,mobile"
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

        result = {
            "ip": "?", "pure_score": "?", "pure_emoji": "❓",
            "ip_attr": "未知", "ip_src": "未知",
            "error": None, "source": "ipapi",
        }

        req_timeout = timeout or config.request_timeout
        # ip-api 免费版约 45 次/分钟限速: 遇 429/网络错误时最多重试 2 次(退避 1s/2s)
        max_attempts = 3
        last_err = None
        for attempt in range(max_attempts):
            try:
                async with AsyncSession(proxies=proxies, impersonate="chrome124", timeout=req_timeout) as session:
                    resp = await session.get(url)
                    if resp.status_code == 429:
                        # 限流: 退避后重试
                        last_err = f"HTTP 429 (rate limited)"
                        if attempt < max_attempts - 1:
                            await asyncio.sleep(1 * (attempt + 1))
                            continue
                        result["error"] = "ip-api 限流(45次/分),请稍后再试"
                        return result
                    if resp.status_code != 200:
                        result["error"] = f"HTTP {resp.status_code}"
                        return result
                    data = resp.json()
                    if data.get("status") != "success":
                        result["error"] = data.get("message", "ip-api 查询失败")
                        return result

                    result["ip"] = data.get("query", "?")

                    # 启发式风险度
                    score = self._score_risk(data)
                    result["pure_score"] = f"{score}%"
                    result["pure_emoji"] = self.get_emoji(result["pure_score"])

                    # 属性判断: 机房 / 住宅(与评分用同一套判定,保持一致)
                    hosting = bool(data.get("hosting"))
                    org = str(data.get("org", "") or "") + " " + str(data.get("isp", "") or "")
                    result["ip_attr"] = "机房" if self._is_cloud_ip(org) or (hosting and not self._is_residential_org(org)) else "住宅"

                    # 原生 / 代理
                    result["ip_src"] = "代理" if data.get("proxy") else "原生"

                    # 汇总标注(与 ping0 的 【emoji 属性|来源】 格式一致)
                    result["full_string"] = f"【{result['pure_emoji']} {result['ip_attr']}|{result['ip_src']}】"
                    return result
            except Exception as e:
                last_err = str(e)
                logger.error(f"IP-API check failed (attempt {attempt+1}): {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue

        result["error"] = last_err or "ip-api 查询失败"
        return result

    @staticmethod
    def _is_residential_org(org: str) -> bool:
        """ISP/组织名是否命中明显住宅宽带关键词。"""
        org_lower = (org or "").lower()
        return any(kw in org_lower for kw in RESIDENTIAL_KEYWORDS)

    @classmethod
    def _is_cloud_ip(cls, org: str) -> bool:
        """ISP/组织名是否命中云厂商 ASN 或机房关键词。"""
        org = org or ""
        org_lower = org.lower()
        m = re.search(r"AS(\d+)", org, re.IGNORECASE)
        if m and m.group(1) in CLOUD_ASNS:
            return True
        if any(kw in org_lower for kw in CLOUD_KEYWORDS):
            return True
        return False
