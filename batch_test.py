#!/usr/bin/env python3
"""
IP-Stream-Checker 自动化测试脚本
"""

import asyncio
import argparse
import json
import logging
from datetime import datetime
from app.ip_checker.checker_service import CheckerService
from app.stream_tester.tester_service import TesterService
from config.config import config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def run_batch_test(proxy_url: str = None, providers: list = None):
    """
    运行批量测试
    
    Args:
        proxy_url: 代理URL
        providers: 流媒体提供商列表
        
    Returns:
        测试结果
    """
    # 初始化服务
    ip_checker = CheckerService()
    stream_tester = TesterService(
        providers=config.get("stream_providers", []),
        proxy=proxy_url
    )
    
    # 运行IP检测
    logging.info("开始IP-risk检测...")
    ip_result = await ip_checker.check_ip(proxy_url or "http://127.0.0.1:1080", source="ping0")
    logging.info(f"IP检测结果: {json.dumps(ip_result, indent=2)}")
    
    # 运行流媒体测试
    if providers:
        logging.info(f"开始流媒体测试: {providers}")
        stream_result = await stream_tester.test_stream(providers, proxy=proxy_url)
        logging.info(f"流媒体测试结果: {json.dumps(stream_result, indent=2)}")
    else:
        logging.info("未指定流媒体提供商，跳过流媒体测试")
        stream_result = None
    
    # 整合结果
    final_result = {
        "timestamp": datetime.now().isoformat(),
        "ip_check": ip_result,
        "stream_test": stream_result,
        "summary": {
            "ip_check_success": ip_result.get("success", False),
            "stream_test_completed": stream_result is not None,
            "total_tests": 1 + (len(providers) if providers else 0)
        }
    }
    
    return final_result

def save_results(results: dict, filename: str = None):
    """
    保存测试结果到文件
    
    Args:
        results: 测试结果
        filename: 文件名
    """
    if not filename:
        filename = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logging.info(f"测试结果已保存到: {filename}")

async def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='IP-Stream-Checker 自动化测试')
    parser.add_argument('--proxy', help='代理URL')
    parser.add_argument('--providers', nargs='+', help='流媒体提供商列表')
    parser.add_argument('--output', help='输出文件名')
    
    args = parser.parse_args()
    
    # 运行测试
    results = await run_batch_test(proxy_url=args.proxy, providers=args.providers)
    
    # 保存结果
    save_results(results, args.output)
    
    # 打印结果摘要
    print("\n=== 测试结果摘要 ===")
    print(f"IP检测状态: {'成功' if results['summary']['ip_check_success'] else '失败'}")
    if results['stream_test']:
        print(f"流媒体测试状态: {'完成' if results['summary']['stream_test_completed'] else '未完成'}")
        print(f"总测试数: {results['summary']['total_tests']}")
    
    print(f"\n详细结果已保存到文件")

if __name__ == "__main__":
    asyncio.run(main())