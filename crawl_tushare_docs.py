#!/usr/bin/env python3
"""Tushare API文档爬虫。

将Tushare官方文档爬取并保存为Markdown格式。
"""

import sys
import os
import time
import re
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup

# 输出目录
OUTPUT_DIR = Path(__file__).parent / "APIDOC"
OUTPUT_DIR.mkdir(exist_ok=True)

# Tushare文档基础URL
BASE_URL = "https://tushare.pro/document/2"

# 需要爬取的API文档ID映射（基于实际页面结构）
# ETF相关API
ETF_API_DOCS = {
    # ETF专题
    "fund_basic": {"doc_id": 407, "title": "ETF基本信息", "category": "ETF专题"},
    "fund_daily": {"doc_id": 408, "title": "ETF日线行情", "category": "ETF专题"},
    "fund_share": {"doc_id": 409, "title": "ETF份额规模", "category": "ETF专题"},
    "fund_adj": {"doc_id": 410, "title": "ETF复权因子", "category": "ETF专题"},
    "fund_min_real": {"doc_id": 411, "title": "ETF实时分钟", "category": "ETF专题"},
    "fund_min_his": {"doc_id": 412, "title": "ETF历史分钟", "category": "ETF专题"},
    "fund_daily_real": {"doc_id": 413, "title": "ETF实时日线", "category": "ETF专题"},
    "fund_index": {"doc_id": 414, "title": "ETF基准指数", "category": "ETF专题"},

    # 公募基金相关
    "fund_nav": {"doc_id": 420, "title": "基金净值", "category": "公募基金"},
    "fund_list": {"doc_id": 421, "title": "基金列表", "category": "公募基金"},
    "fund_manager": {"doc_id": 422, "title": "基金管理人", "category": "公募基金"},
    "fund_portfolio": {"doc_id": 425, "title": "基金持仓", "category": "公募基金"},
    "fund_dividend": {"doc_id": 424, "title": "基金分红", "category": "公募基金"},
    "fund_scale": {"doc_id": 423, "title": "基金规模", "category": "公募基金"},
}

# 通用股票API
STOCK_API_DOCS = {
    "stock_basic": {"doc_id": 25, "title": "股票列表", "category": "股票基础"},
    "daily": {"doc_id": 27, "title": "日线行情", "category": "股票行情"},
    "daily_basic": {"doc_id": 32, "title": "每日指标", "category": "股票行情"},
    "trade_cal": {"doc_id": 29, "title": "交易日历", "category": "股票基础"},
    "stk_factor": {"doc_id": 161, "title": "股票技术面因子", "category": "特色数据"},
}

# 指数相关API
INDEX_API_DOCS = {
    "index_basic": {"doc_id": 317, "title": "指数基本信息", "category": "指数专题"},
    "index_daily": {"doc_id": 318, "title": "指数日线行情", "category": "指数专题"},
    "index_weight": {"doc_id": 321, "title": "指数成分和权重", "category": "指数专题"},
    "index_classify": {"doc_id": 322, "title": "申万行业分类", "category": "指数专题"},
}

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


def fetch_doc_content(doc_id: int) -> str:
    """获取文档页面HTML内容。"""
    url = f"{BASE_URL}?doc_id={doc_id}"
    print(f"  Fetching: {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.encoding = 'utf-8'
        return response.text
    except Exception as e:
        print(f"  [Error] Failed to fetch doc_id={doc_id}: {e}")
        return ""


def parse_html_to_markdown(html: str, title: str, category: str) -> str:
    """将HTML内容解析为Markdown格式。"""
    soup = BeautifulSoup(html, 'html.parser')

    # 查找文档内容区域
    content_div = soup.find('div', class_='tui-editor-contents')
    if not content_div:
        content_div = soup.find('div', {'id': 'content'})
    if not content_div:
        content_div = soup.find('article')
    if not content_div:
        content_div = soup.find('div', class_='content')

    if not content_div:
        return ""

    # 转换为Markdown
    md_content = []

    # 标题
    md_content.append(f"# {title}\n")
    md_content.append(f"> 分类: {category}\n")
    md_content.append(f"> 来源: Tushare Pro 文档\n\n")
    md_content.append("---\n\n")

    # 遍历内容
    for element in content_div.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'table', 'pre', 'ul', 'ol', 'blockquote']):
        if element.name in ['h1', 'h2', 'h3', 'h4']:
            level = int(element.name[1])
            text = element.get_text(strip=True)
            md_content.append(f"\n{'#' * level} {text}\n")

        elif element.name == 'p':
            text = process_inline_elements(element)
            if text.strip():
                md_content.append(f"\n{text}\n")

        elif element.name == 'pre':
            code = element.get_text()
            md_content.append(f"\n```\n{code}\n```\n")

        elif element.name == 'table':
            md_table = convert_table_to_markdown(element)
            md_content.append(f"\n{md_table}\n")

        elif element.name == 'ul':
            for li in element.find_all('li', recursive=False):
                text = li.get_text(strip=True)
                md_content.append(f"- {text}")

        elif element.name == 'ol':
            for i, li in enumerate(element.find_all('li', recursive=False), 1):
                text = li.get_text(strip=True)
                md_content.append(f"{i}. {text}")

        elif element.name == 'blockquote':
            text = element.get_text(strip=True)
            md_content.append(f"\n> {text}\n")

    return '\n'.join(md_content)


def process_inline_elements(element) -> str:
    """处理行内元素（链接、代码、加粗等）。"""
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
            cell_text = cell.get_text(strip=True)
            # 处理单元格内的换行
            cell_text = cell_text.replace('\n', ' ')
            cells.append(cell_text)
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    # 确定列数
    max_cols = max(len(row) for row in rows)

    # 构建Markdown表格
    md_lines = []

    # 表头
    header = rows[0]
    while len(header) < max_cols:
        header.append('')
    md_lines.append('| ' + ' | '.join(header) + ' |')

    # 分隔线
    md_lines.append('| ' + ' | '.join(['---'] * max_cols) + ' |')

    # 数据行
    for row in rows[1:]:
        while len(row) < max_cols:
            row.append('')
        md_lines.append('| ' + ' | '.join(row) + ' |')

    return '\n'.join(md_lines)


def crawl_api_doc(api_name: str, doc_info: dict) -> bool:
    """爬取单个API文档。"""
    doc_id = doc_info["doc_id"]
    title = doc_info["title"]
    category = doc_info["category"]

    print(f"\n[{api_name}] {title} (doc_id={doc_id})")

    # 获取HTML
    html = fetch_doc_content(doc_id)
    if not html:
        print(f"  [Skip] No content fetched")
        return False

    # 解析为Markdown
    md_content = parse_html_to_markdown(html, title, category)
    if not md_content or len(md_content) < 100:
        print(f"  [Skip] Content too short or parsing failed")
        return False

    # 保存文件
    category_dir = OUTPUT_DIR / category
    category_dir.mkdir(exist_ok=True)

    filename = f"{api_name}.md"
    filepath = category_dir / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"  [OK] Saved to {filepath.relative_to(OUTPUT_DIR)}")
    return True


def create_index_file():
    """创建文档索引文件。"""
    index_content = """# Tushare API 文档索引

> 本文档由爬虫自动生成，来源：https://tushare.pro/document/2

## 目录

"""

    # 遍历目录结构
    categories = {}
    for md_file in OUTPUT_DIR.rglob("*.md"):
        if md_file.name == "index.md":
            continue
        category = md_file.parent.name
        if category not in categories:
            categories[category] = []
        categories[category].append(md_file)

    # 生成索引
    for category in sorted(categories.keys()):
        index_content += f"\n### {category}\n\n"
        for md_file in sorted(categories[category]):
            rel_path = md_file.relative_to(OUTPUT_DIR)
            # 读取文件标题
            with open(md_file, 'r', encoding='utf-8') as f:
                first_line = f.readline()
                title = first_line.replace('#', '').strip() if first_line.startswith('#') else md_file.stem
            index_content += f"- [{title}]({rel_path})\n"

    # 保存索引
    index_path = OUTPUT_DIR / "index.md"
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_content)

    print(f"\n[Index] Created {index_path}")


def main():
    print("=" * 60)
    print("  Tushare API 文档爬虫")
    print("=" * 60)

    # 合并所有需要爬取的文档
    all_docs = {}
    all_docs.update(ETF_API_DOCS)
    all_docs.update(STOCK_API_DOCS)
    all_docs.update(INDEX_API_DOCS)

    print(f"\n待爬取文档数量: {len(all_docs)}")

    success_count = 0
    fail_count = 0

    for api_name, doc_info in all_docs.items():
        try:
            if crawl_api_doc(api_name, doc_info):
                success_count += 1
            else:
                fail_count += 1
            # 礼貌延迟
            time.sleep(1)
        except Exception as e:
            print(f"  [Error] {e}")
            fail_count += 1

    # 创建索引
    create_index_file()

    print("\n" + "=" * 60)
    print(f"  爬取完成: 成功 {success_count}, 失败 {fail_count}")
    print(f"  文档目录: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
