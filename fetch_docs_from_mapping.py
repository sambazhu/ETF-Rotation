#!/usr/bin/env python3
"""使用已保存的doc_id映射和MCP web-reader风格的方式获取文档内容"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

MAPPING_FILE = Path(__file__).parent / "APIDOC" / "doc_id_mapping.json"
OUTPUT_FILE = Path(__file__).parent / "APIDOC" / "tushare_api_reference.md"

BASE_URL = "https://tushare.pro/document/2"

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch_page_content(doc_id: str) -> Tuple[str, str]:
    """获取单个页面的内容"""
    url = f"{BASE_URL}?doc_id={doc_id}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.encoding = 'utf-8'
        html = response.text

        soup = BeautifulSoup(html, 'html.parser')

        # 查找内容区域
        content_div = soup.find('div', class_='tui-editor-contents')
        if not content_div:
            content_div = soup.find('div', {'id': 'content'})
        if not content_div:
            content_div = soup.find('article')

        if not content_div:
            return None, None

        # 提取标题
        title = None
        for tag in ['h1', 'h2', 'h3']:
            h = content_div.find(tag)
            if h:
                title = h.get_text(strip=True)
                break

        if not title:
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text(strip=True).replace(' - Tushare', '')

        if not title:
            return None, None

        # 检查是否包含API相关关键词
        text = content_div.get_text()
        if len(text) < 200:
            return None, None

        # 转换为Markdown
        md_content = html_to_markdown(content_div, title)
        return title, md_content

    except Exception as e:
        print(f"  [Error] doc_id={doc_id}: {e}")
        return None, None


def html_to_markdown(content_div, title: str) -> str:
    """将HTML内容转换为Markdown"""
    md_lines = [f"### {title}\n"]

    for element in content_div.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'table', 'pre', 'ul', 'ol', 'blockquote'], recursive=False):
        if element.name in ['h1', 'h2', 'h3', 'h4', 'h5']:
            level = int(element.name[1])
            text = element.get_text(strip=True)
            if text and text != title:
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
    """处理行内元素"""
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
    """将HTML表格转换为Markdown表格"""
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

    header = rows[0]
    while len(header) < max_cols:
        header.append('')
    md_lines.append('| ' + ' | '.join(header) + ' |')
    md_lines.append('| ' + ' | '.join(['---'] * max_cols) + ' |')

    for row in rows[1:]:
        while len(row) < max_cols:
            row.append('')
        md_lines.append('| ' + ' | '.join(row) + ' |')

    return '\n'.join(md_lines)


def categorize_by_parent(doc_id: str, mapping: Dict, parent_stack: List[str]) -> str:
    """根据父节点确定分类"""
    item = mapping.get(doc_id, {})

    # 找到最近的非叶子父节点
    for parent in reversed(parent_stack):
        if parent and not mapping.get(parent, {}).get('is_leaf', True):
            parent_text = mapping.get(parent, {}).get('text', '')
            if parent_text:
                return parent_text

    return '其他'


def generate_markdown_doc(results: Dict[str, Tuple[str, str, str]], output_file: Path):
    """生成Markdown文档"""
    print(f"\n生成文档: {output_file}")

    # 按分类组织
    categorized = {}
    for title, (category, content, doc_id) in results.items():
        if category not in categorized:
            categorized[category] = []
        categorized[category].append((title, content, doc_id))

    # 生成文档
    doc_lines = [
        "# Tushare API 完整参考文档",
        "",
        "> 本文档由爬虫自动生成",
        f"> 来源: {BASE_URL}",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
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
        doc_lines.append(f'<a id="{anchor}"></a>')
        doc_lines.append(f"## {category}")
        doc_lines.append("")
        doc_lines.append("---")
        doc_lines.append("")

        for title, content, doc_id in sorted(categorized[category]):
            doc_lines.append(f"<!-- doc_id: {doc_id} -->")
            doc_lines.append(content)
            doc_lines.append("")
            doc_lines.append("---")
            doc_lines.append("")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(doc_lines))

    print(f"文档已生成: {output_file}")
    print(f"共收录 {len(results)} 个API接口")


def main():
    print("=" * 60)
    print("  Tushare API 文档获取 - 使用doc_id映射")
    print("=" * 60)

    # 加载映射
    with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
        mapping = json.load(f)

    print(f"\n加载了 {len(mapping)} 个doc_id映射")

    # 获取叶子节点
    leaf_items = [(doc_id, info) for doc_id, info in mapping.items() if info.get('is_leaf', True)]
    print(f"其中 {len(leaf_items)} 个是API文档页面")

    # 构建分类路径
    # 根据doc_id顺序推断父子关系
    sorted_ids = sorted(mapping.keys(), key=lambda x: int(x))

    # 分类映射
    category_map = {
        '股票数据': '股票数据',
        '基础数据': '股票数据/基础数据',
        '行情数据': '股票数据/行情数据',
        '财务数据': '股票数据/财务数据',
        '参考数据': '股票数据/参考数据',
        '特色数据': '股票数据/特色数据',
        '两融及转融通': '股票数据/两融及转融通',
        '资金流向数据': '股票数据/资金流向',
        '打板专题数据': '股票数据/打板专题',
        'ETF专题': 'ETF专题',
        '指数专题': '指数专题',
        '公募基金': '公募基金',
        '期货数据': '期货数据',
        '现货数据': '现货数据',
        '期权数据': '期权数据',
        '债券专题': '债券专题',
        '外汇数据': '外汇数据',
        '港股数据': '港股数据',
        '美股数据': '美股数据',
        '行业经济': '行业经济',
        '宏观经济': '宏观经济',
        '大模型语料专题数据': '大模型语料',
        '财富管理': '财富管理',
    }

    # 追踪当前分类
    current_category = '其他'
    parent_stack = []

    # 爬取内容
    results = {}

    for i, (doc_id, info) in enumerate(leaf_items, 1):
        text = info.get('text', '')

        # 更新分类（如果是分类节点）
        if not info.get('is_leaf', True):
            if text in category_map:
                current_category = category_map[text]
                parent_stack.append(doc_id)
            continue

        print(f"  [{i}/{len(leaf_items)}] 爬取: {text} (doc_id={doc_id})")

        title, content = fetch_page_content(doc_id)

        if title and content:
            # 使用父节点文本作为分类
            parent_text = ''
            for pid in reversed(parent_stack):
                pinfo = mapping.get(pid, {})
                if not pinfo.get('is_leaf', True):
                    parent_text = pinfo.get('text', '')
                    break

            category = category_map.get(parent_text, current_category)
            results[title] = (category, content, doc_id)
            print(f"    -> 成功: {title}")
        else:
            print(f"    -> 跳过: 无有效内容")

        time.sleep(0.2)

    generate_markdown_doc(results, OUTPUT_FILE)

    print("\n" + "=" * 60)
    print("  完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
