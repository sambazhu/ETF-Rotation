#!/usr/bin/env python3
"""Tushare API文档爬虫 - 完整版

扫描所有doc_id，整理成单个MD文档，方便大模型查询。
"""

import sys
import os
import time
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup

# 输出文件
OUTPUT_FILE = Path(__file__).parent / "APIDOC" / "tushare_api_reference.md"

# Tushare文档基础URL
BASE_URL = "https://tushare.pro/document/2"

# 分类映射 - 基于导航结构
CATEGORY_MAPPING = {
    # 股票数据-基础数据
    "股票列表": "股票数据/基础数据",
    "每日股本": "股票数据/基础数据",
    "交易日历": "股票数据/基础数据",
    "ST股票": "股票数据/基础数据",
    "沪深港通股票": "股票数据/基础数据",
    "股票曾用名": "股票数据/基础数据",
    "上市公司": "股票数据/基础数据",
    "管理层": "股票数据/基础数据",
    "北交所": "股票数据/基础数据",
    "IPO": "股票数据/基础数据",
    "股票历史": "股票数据/基础数据",

    # 股票数据-行情数据
    "日线行情": "股票数据/行情数据",
    "日线": "股票数据/行情数据",
    "分钟": "股票数据/行情数据",
    "周线": "股票数据/行情数据",
    "月线": "股票数据/行情数据",
    "复权": "股票数据/行情数据",
    "Tick": "股票数据/行情数据",
    "成交": "股票数据/行情数据",
    "每日指标": "股票数据/行情数据",
    "通用行情": "股票数据/行情数据",
    "涨跌停": "股票数据/行情数据",
    "停复牌": "股票数据/行情数据",
    "十大成交": "股票数据/行情数据",
    "成交统计": "股票数据/行情数据",

    # 股票数据-财务数据
    "利润表": "股票数据/财务数据",
    "资产负债": "股票数据/财务数据",
    "现金流量": "股票数据/财务数据",
    "业绩": "股票数据/财务数据",
    "分红": "股票数据/财务数据",
    "财务指标": "股票数据/财务数据",
    "审计": "股票数据/财务数据",
    "主营": "股票数据/财务数据",
    "财报": "股票数据/财务数据",

    # 股票数据-参考数据
    "股东": "股票数据/参考数据",
    "质押": "股票数据/参考数据",
    "回购": "股票数据/参考数据",
    "解禁": "股票数据/参考数据",
    "大宗交易": "股票数据/参考数据",
    "开户": "股票数据/参考数据",

    # 股票数据-特色数据
    "盈利预测": "股票数据/特色数据",
    "筹码": "股票数据/特色数据",
    "技术面因子": "股票数据/特色数据",
    "结算": "股票数据/特色数据",
    "持股": "股票数据/特色数据",
    "竞价": "股票数据/特色数据",
    "九转": "股票数据/特色数据",
    "AH股": "股票数据/特色数据",
    "调研": "股票数据/特色数据",
    "金股": "股票数据/特色数据",

    # 股票数据-两融
    "融资融券": "股票数据/两融",
    "转融": "股票数据/两融",
    "借券": "股票数据/两融",

    # 股票数据-资金流向
    "资金流向": "股票数据/资金流向",

    # 股票数据-打板
    "龙虎榜": "股票数据/打板专题",
    "涨停": "股票数据/打板专题",
    "板块": "股票数据/打板专题",
    "游资": "股票数据/打板专题",
    "热榜": "股票数据/打板专题",
    "通达信": "股票数据/打板专题",
    "题材": "股票数据/打板专题",
    "异动": "股票数据/打板专题",

    # ETF专题
    "ETF": "ETF专题",

    # 指数专题
    "指数": "指数专题",
    "申万": "指数专题",
    "中信": "指数专题",

    # 公募基金
    "基金": "公募基金",

    # 期货
    "期货": "期货数据",
    "合约": "期货数据",
    "仓单": "期货数据",
    "持仓排名": "期货数据",
    "南华": "期货数据",
    "主力": "期货数据",

    # 现货
    "黄金": "现货数据",

    # 期权
    "期权": "期权数据",

    # 债券
    "可转债": "债券专题",
    "债券": "债券专题",
    "国债": "债券专题",

    # 外汇
    "外汇": "外汇数据",

    # 港股
    "港股": "港股数据",

    # 美股
    "美股": "美股数据",

    # 宏观
    "GDP": "宏观经济",
    "CPI": "宏观经济",
    "PPI": "宏观经济",
    "PMI": "宏观经济",
    "利率": "宏观经济",
    "货币": "宏观经济",
    "社融": "宏观经济",

    # 其他
    "电影": "行业经济",
    "电视剧": "行业经济",
}

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


def categorize_by_title(title: str) -> str:
    """根据标题推断分类。"""
    for keyword, category in CATEGORY_MAPPING.items():
        if keyword in title:
            return category
    return "其他"


def fetch_page(doc_id: int) -> Tuple[int, Optional[str], Optional[str]]:
    """获取单个页面内容。"""
    url = f"{BASE_URL}?doc_id={doc_id}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.encoding = 'utf-8'
        html = response.text

        # 解析HTML
        soup = BeautifulSoup(html, 'html.parser')

        # 查找内容区域
        content_div = soup.find('div', class_='tui-editor-contents')
        if not content_div:
            content_div = soup.find('div', {'id': 'content'})
        if not content_div:
            content_div = soup.find('article')

        if not content_div:
            return doc_id, None, None

        # 提取标题
        title = None
        for tag in ['h1', 'h2', 'h3']:
            h = content_div.find(tag)
            if h:
                title = h.get_text(strip=True)
                break

        if not title:
            # 尝试从其他地方获取标题
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text(strip=True).replace(' - Tushare', '')

        if not title:
            return doc_id, None, None

        # 检查是否是有效的API文档页面
        text = content_div.get_text()
        if len(text) < 200:
            return doc_id, None, None

        # 检查是否包含API相关关键词
        api_keywords = ['接口', '参数', '输出', '示例', 'ts_code', 'pro.', '描述']
        if not any(kw in text for kw in api_keywords):
            return doc_id, None, None

        # 转换为Markdown
        md_content = html_to_markdown(content_div, title)
        return doc_id, title, md_content

    except Exception as e:
        print(f"  [Error] doc_id={doc_id}: {e}")
        return doc_id, None, None


def html_to_markdown(content_div, title: str) -> str:
    """将HTML内容转换为Markdown。"""
    md_lines = [f"## {title}\n"]

    for element in content_div.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'table', 'pre', 'ul', 'ol', 'blockquote']):
        if element.name in ['h1', 'h2', 'h3', 'h4', 'h5']:
            level = int(element.name[1])
            text = element.get_text(strip=True)
            if text and text != title:  # 避免重复标题
                md_lines.append(f"\n{'#' * level} {text}\n")

        elif element.name == 'p':
            text = process_inline_elements(element)
            if text.strip():
                md_lines.append(f"\n{text}\n")

        elif element.name == 'pre':
            code = element.get_text()
            if code.strip():
                md_lines.append(f"\n```\n{code.strip()}\n```\n")

        elif element.name == 'table':
            md_table = convert_table_to_markdown(element)
            if md_table:
                md_lines.append(f"\n{md_table}\n")

        elif element.name == 'ul':
            for li in element.find_all('li', recursive=False):
                text = li.get_text(strip=True)
                if text:
                    md_lines.append(f"- {text}")

        elif element.name == 'ol':
            for i, li in enumerate(element.find_all('li', recursive=False), 1):
                text = li.get_text(strip=True)
                if text:
                    md_lines.append(f"{i}. {text}")

        elif element.name == 'blockquote':
            text = element.get_text(strip=True)
            if text:
                md_lines.append(f"\n> {text}\n")

    return '\n'.join(md_lines)


def process_inline_elements(element) -> str:
    """处理行内元素。"""
    text_parts = []
    for child in element.children:
        if isinstance(child, str):
            text_parts.append(child)
        elif child.name == 'code':
            text_parts.append(f"`{child.get_text()}`")
        elif child.name == 'a':
            href = child.get('href', '')
            link_text = child.get_text()
            text_parts.append(f"[{link_text}]({href})")
        elif child.name == 'strong' or child.name == 'b':
            text_parts.append(f"**{child.get_text()}**")
        elif child.name == 'em' or child.name == 'i':
            text_parts.append(f"*{child.get_text()}*")
        elif child.name == 'br':
            text_parts.append('\n')
        else:
            text_parts.append(child.get_text())
    return ''.join(text_parts)


def convert_table_to_markdown(table) -> str:
    """将HTML表格转换为Markdown表格。"""
    rows = []
    for tr in table.find_all('tr'):
        cells = []
        for cell in tr.find_all(['th', 'td']):
            cell_text = cell.get_text(strip=True).replace('\n', ' ')
            cells.append(cell_text)
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    max_cols = max(len(row) for row in rows)
    md_lines = []

    # 表头
    header = rows[0]
    while len(header) < max_cols:
        header.append('')
    md_lines.append('| ' + ' | '.join(header) + ' |')
    md_lines.append('| ' + ' | '.join(['---'] * max_cols) + ' |')

    # 数据行
    for row in rows[1:]:
        while len(row) < max_cols:
            row.append('')
        md_lines.append('| ' + ' | '.join(row) + ' |')

    return '\n'.join(md_lines)


def scan_doc_ids(start: int = 1, end: int = 500, workers: int = 5) -> Dict[str, Tuple[str, str]]:
    """扫描doc_id范围，收集有效页面。"""
    print(f"扫描 doc_id 范围: {start} - {end}")
    print("=" * 60)

    results = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_page, doc_id): doc_id for doc_id in range(start, end + 1)}

        completed = 0
        for future in as_completed(futures):
            doc_id, title, content = future.result()
            completed += 1

            if title and content:
                category = categorize_by_title(title)
                results[title] = (category, content)
                print(f"  [{completed}/{end-start+1}] doc_id={doc_id}: {title} -> {category}")
            else:
                if completed % 50 == 0:
                    print(f"  [{completed}/{end-start+1}] 已扫描...")

            # 礼貌延迟
            time.sleep(0.1)

    return results


def generate_markdown_doc(results: Dict[str, Tuple[str, str]], output_file: Path):
    """生成单个Markdown文档。"""
    print(f"\n生成文档: {output_file}")

    # 按分类组织
    categorized = {}
    for title, (category, content) in results.items():
        if category not in categorized:
            categorized[category] = []
        categorized[category].append((title, content))

    # 生成文档
    doc_lines = [
        "# Tushare API 完整参考文档",
        "",
        "> 本文档由爬虫自动生成",
        "> 来源: https://tushare.pro/document/2",
        "> 生成时间: " + time.strftime("%Y-%m-%d %H:%M:%S"),
        "",
        "---",
        "",
        "## 目录",
        "",
    ]

    # 添加目录
    for category in sorted(categorized.keys()):
        count = len(categorized[category])
        anchor = category.replace('/', '_').replace(' ', '_')
        doc_lines.append(f"- [{category}](#{anchor}) ({count}个接口)")

    doc_lines.append("")
    doc_lines.append("---")
    doc_lines.append("")

    # 添加各分类内容
    for category in sorted(categorized.keys()):
        anchor = category.replace('/', '_').replace(' ', '_')
        doc_lines.append(f"<a id=\"{anchor}\"></a>")
        doc_lines.append(f"## {category}")
        doc_lines.append("")
        doc_lines.append("---")
        doc_lines.append("")

        for title, content in sorted(categorized[category]):
            doc_lines.append(content)
            doc_lines.append("")
            doc_lines.append("---")
            doc_lines.append("")

    # 写入文件
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(doc_lines))

    print(f"文档已生成: {output_file}")
    print(f"共收录 {len(results)} 个API接口")


def main():
    print("=" * 60)
    print("  Tushare API 文档爬虫 - 完整版")
    print("=" * 60)

    # 扫描doc_id范围
    # Tushare的doc_id大概在1-500范围内
    results = scan_doc_ids(start=1, end=500, workers=5)

    # 生成单个Markdown文档
    generate_markdown_doc(results, OUTPUT_FILE)

    print("\n" + "=" * 60)
    print("  爬取完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
