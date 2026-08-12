#!/usr/bin/env python3
"""
IP-Stream-Checker 报告生成脚本
"""

import argparse
import json
import logging
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def load_results(filename: str) -> dict:
    """
    加载测试结果文件
    
    Args:
        filename: 结果文件名
        
    Returns:
        测试结果
    """
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_html_report(results: dict, output_filename: str = None):
    """
    生成HTML报告
    
    Args:
        results: 测试结果
        output_filename: 输出文件名
    """
    # 设置Jinja2环境
    env = Environment(loader=FileSystemLoader('app/web/templates'))
    template = env.get_template('report_template.html')
    
    # 生成报告内容
    report_content = template.render(results=results)
    
    # 保存报告
    if not output_filename:
        output_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    logging.info(f"HTML报告已生成: {output_filename}")

def generate_text_report(results: dict, output_filename: str = None):
    """
    生成文本报告
    
    Args:
        results: 测试结果
        output_filename: 输出文件名
    """
    report_lines = []
    
    # 报告标题
    report_lines.append("=== IP-Stream-Checker 测试报告 ===")
    report_lines.append(f"生成时间: {results['timestamp']}")
    report_lines.append("")
    
    # IP检测结果
    report_lines.append("=== IP-risk检测结果 ===")
    ip_result = results['ip_check']
    if ip_result['success']:
        report_lines.append(f"IP地址: {ip_result['ip']}")
        report_lines.append(f"国家/地区: {ip_result['country']}")
        report_lines.append(f"城市: {ip_result['city']}")
        report_lines.append(f"ISP: {ip_result['isp']}")
        report_lines.append(f"类型: {ip_result['type']}")
        report_lines.append(f"响应时间: {ip_result['response_time']:.2f}秒")
    else:
        report_lines.append(f"检测失败: {ip_result['error']}")
    report_lines.append("")
    
    # 流媒体测试结果
    if results['stream_test']:
        report_lines.append("=== 流媒体测试结果 ===")
        stream_result = results['stream_test']
        report_lines.append(f"总测试数: {stream_result['total_providers']}")
        report_lines.append(f"成功: {stream_result['successful_tests']}")
        report_lines.append(f"失败: {stream_result['failed_tests']}")
        report_lines.append("")
        
        for detail in stream_result['details']:
            status = "✅ 可用" if detail['success'] else "❌ 不可用"
            region = f" ({detail['region']})" if detail['region'] != 'unknown' else ""
            report_lines.append(f"{detail['provider']}{region}: {status}")
            report_lines.append(f"  消息: {detail['message']}")
            report_lines.append(f"  响应时间: {detail['response_time']:.2f}秒")
            report_lines.append("")
    
    # 保存报告
    if not output_filename:
        output_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    
    logging.info(f"文本报告已生成: {output_filename}")

async def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='IP-Stream-Checker 报告生成')
    parser.add_argument('results_file', help='测试结果文件')
    parser.add_argument('--output', help='输出文件名')
    parser.add_argument('--format', choices=['html', 'text'], default='html', help='输出格式')
    
    args = parser.parse_args()
    
    # 加载结果
    results = load_results(args.results_file)
    
    # 生成报告
    if args.format == 'html':
        generate_html_report(results, args.output)
    else:
        generate_text_report(results, args.output)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())