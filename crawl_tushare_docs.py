#!/usr/bin/env python3
"""Tushare API文档爬虫 - 使用Selenium模拟点击导航

通过展开左侧导航目录，获取每个API对应的doc_id和内容。
"""

import sys
import os
import time
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager

# 输出文件
OUTPUT_FILE = Path(__file__).parent / "APIDOC" / "tushare_api_reference.md"
MAPPING_FILE = Path(__file__).parent / "APIDOC" / "doc_id_mapping.json"

# Tushare文档基础URL
BASE_URL = "https://tushare.pro/document/2"


def setup_driver():
    """设置Chrome WebDriver"""
    options = Options()
    options.add_argument('--headless')  # 无头模式
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def wait_for_page_load(driver, timeout=10):
    """等待页面加载完成"""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
    except TimeoutException:
        pass


def expand_all_nodes(driver):
    """展开所有jsTree节点"""
    print("展开所有导航节点...")

    max_attempts = 10
    for attempt in range(max_attempts):
        # 找到所有闭合的节点（有子节点但未展开的）
        closed_nodes = driver.find_elements(By.CSS_SELECTOR, ".jstree-closed > .jstree-ocl")

        if not closed_nodes:
            print(f"  所有节点已展开 (尝试次数: {attempt + 1})")
            break

        print(f"  尝试 {attempt + 1}: 发现 {len(closed_nodes)} 个闭合节点")

        # 点击展开每个闭合节点
        for node in closed_nodes:
            try:
                # 滚动到元素可见
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", node)
                time.sleep(0.05)
                node.click()
                time.sleep(0.05)
            except Exception as e:
                continue

        time.sleep(0.5)

    # 最终等待
    time.sleep(1)


def get_navigation_items(driver) -> List[Dict]:
    """获取导航目录中的所有项目及其doc_id"""
    print("正在获取导航目录结构...")

    # 等待jsTree加载
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "jstree-anchor"))
        )
    except TimeoutException:
        print("警告: 导航目录加载超时")

    # 展开所有节点
    expand_all_nodes(driver)

    items = []

    # 获取所有导航链接
    anchors = driver.find_elements(By.CSS_SELECTOR, ".jstree-anchor")
    print(f"找到 {len(anchors)} 个导航项")

    for anchor in anchors:
        try:
            # 获取链接文本
            text = anchor.text.strip()

            # 获取href属性
            href = anchor.get_attribute('href')

            if href and 'doc_id=' in href:
                # 提取doc_id
                match = re.search(r'doc_id=(\d+)', href)
                if match:
                    doc_id = match.group(1)

                    # 获取父节点li
                    parent_li = anchor.find_element(By.XPATH, '..')

                    # 判断是否有子节点（展开后的子节点）
                    has_children = len(parent_li.find_elements(By.CSS_SELECTOR, ':scope > ul > li')) > 0

                    items.append({
                        'text': text,
                        'doc_id': doc_id,
                        'href': href,
                        'is_leaf': not has_children
                    })

        except StaleElementReferenceException:
            continue
        except Exception as e:
            continue

    return items


def fetch_page_content(driver, doc_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """获取单个页面的内容"""
    url = f"{BASE_URL}?doc_id={doc_id}"

    try:
        driver.get(url)
        wait_for_page_load(driver, timeout=10)
        time.sleep(0.5)

        # 获取内容区域
        try:
            content_div = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".tui-editor-contents"))
            )
        except TimeoutException:
            try:
                content_div = driver.find_element(By.ID, "content")
            except NoSuchElementException:
                return None, None, None

        # 提取标题
        title = None
        try:
            h1 = content_div.find_element(By.TAG_NAME, "h1")
            title = h1.text.strip()
        except NoSuchElementException:
            try:
                h2 = content_div.find_element(By.TAG_NAME, "h2")
                title = h2.text.strip()
            except NoSuchElementException:
                pass

        if not title:
            page_title = driver.title
            if ' - ' in page_title:
                title = page_title.split(' - ')[0]
            else:
                title = f"doc_{doc_id}"

        # 获取HTML内容
        html_content = content_div.get_attribute('innerHTML')

        # 转换为Markdown
        md_content = html_to_markdown(html_content, title)

        return title, md_content, doc_id

    except Exception as e:
        print(f"  [Error] doc_id={doc_id}: {e}")
        return None, None, None


def html_to_markdown(html: str, title: str) -> str:
    """将HTML内容转换为Markdown"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, 'html.parser')
    md_lines = [f"### {title}\n"]

    for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'table', 'pre', 'ul', 'ol', 'blockquote'], recursive=False):
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


def categorize_item(title: str, parent_text: str = '') -> str:
    """根据标题和父节点确定分类"""
    # 父节点到分类的映射
    parent_mapping = {
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

    if parent_text in parent_mapping:
        return parent_mapping[parent_text]

    # 根据标题关键词分类
    category_mapping = {
        '股票': '股票数据',
        '日线': '股票数据/行情数据',
        '分钟': '股票数据/行情数据',
        '复权': '股票数据/行情数据',
        '指标': '股票数据/行情数据',
        '利润': '股票数据/财务数据',
        '资产': '股票数据/财务数据',
        '现金': '股票数据/财务数据',
        '业绩': '股票数据/财务数据',
        '分红': '股票数据/财务数据',
        '股东': '股票数据/参考数据',
        '大宗': '股票数据/参考数据',
        'ETF': 'ETF专题',
        '指数': '指数专题',
        '基金': '公募基金',
        '期货': '期货数据',
        '债券': '债券专题',
        '可转债': '债券专题',
        '港股': '港股数据',
        '美股': '美股数据',
        '外汇': '外汇数据',
        '期权': '期权数据',
        '宏观': '宏观经济',
    }

    for keyword, category in category_mapping.items():
        if keyword in title:
            return category

    return '其他'


def generate_markdown_doc(results: Dict[str, Tuple[str, str, str]], output_file: Path):
    """生成单个Markdown文档"""
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
    print("  Tushare API 文档爬虫 - Selenium版")
    print("=" * 60)

    driver = None
    try:
        print("\n初始化浏览器...")
        driver = setup_driver()

        print(f"\n访问: {BASE_URL}")
        driver.get(BASE_URL)
        wait_for_page_load(driver, timeout=15)
        time.sleep(2)

        # 获取导航目录（包含展开操作）
        nav_items = get_navigation_items(driver)

        if not nav_items:
            print("错误: 未能获取导航目录")
            return

        # 保存映射关系
        mapping = {}
        for item in nav_items:
            mapping[item['doc_id']] = {
                'text': item['text'],
                'href': item['href'],
                'is_leaf': item['is_leaf']
            }

        MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
        print(f"\ndoc_id映射已保存: {MAPPING_FILE}")

        # 统计
        leaf_items = [item for item in nav_items if item['is_leaf']]
        category_items = [item for item in nav_items if not item['is_leaf']]
        print(f"\n发现 {len(category_items)} 个分类页面, {len(leaf_items)} 个API文档页面")

        # 爬取叶子节点（具体的API文档页面）
        print("\n开始爬取API文档...")
        results = {}

        # 构建父子关系映射
        parent_map = build_parent_map(nav_items)

        for i, item in enumerate(leaf_items, 1):
            doc_id = item['doc_id']
            parent_text = parent_map.get(doc_id, '')
            print(f"  [{i}/{len(leaf_items)}] 爬取: {item['text']} (doc_id={doc_id})")

            title, content, _ = fetch_page_content(driver, doc_id)

            if title and content:
                category = categorize_item(title, parent_text)
                results[title] = (category, content, doc_id)
                print(f"    -> 成功: {title}")

            time.sleep(0.3)

        generate_markdown_doc(results, OUTPUT_FILE)

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if driver:
            driver.quit()

    print("\n" + "=" * 60)
    print("  爬取完成!")
    print("=" * 60)


def build_parent_map(nav_items: List[Dict]) -> Dict[str, str]:
    """构建doc_id到父节点文本的映射"""
    # 简单实现：根据列表顺序推断
    parent_map = {}
    current_parent = ''

    for item in nav_items:
        if not item['is_leaf']:
            current_parent = item['text']
        else:
            parent_map[item['doc_id']] = current_parent

    return parent_map


if __name__ == "__main__":
    main()
