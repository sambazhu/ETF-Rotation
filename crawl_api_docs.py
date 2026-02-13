#!/usr/bin/env python3
"""Tushare API文档爬虫 - 基于层次化doc_id_mapping.json，使用Selenium"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)  # 行缓冲

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

MAPPING_FILE = Path(__file__).parent / "APIDOC" / "doc_id_mapping.json"
OUTPUT_FILE = Path(__file__).parent / "APIDOC" / "tushare_api_reference.md"

BASE_URL = "https://tushare.pro/document/2"


def setup_driver():
    """设置Chrome WebDriver"""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    # 使用本地 chromedriver.exe
    chromedriver_path = Path(__file__).parent / "chromedriver.exe"

    if chromedriver_path.exists():
        print(f"使用本地ChromeDriver: {chromedriver_path}")
        service = Service(str(chromedriver_path))
        driver = webdriver.Chrome(service=service, options=options)
        return driver

    # 尝试使用系统PATH中的ChromeDriver
    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception as e:
        print(f"尝试使用系统ChromeDriver失败: {e}")

    raise RuntimeError(f"无法初始化Chrome WebDriver。请确保 chromedriver.exe 存在于: {chromedriver_path}")


def fetch_page_content(driver, doc_id: str) -> Tuple[Optional[str], Optional[str]]:
    """获取单个页面的内容"""
    url = f"{BASE_URL}?doc_id={doc_id}"

    try:
        driver.get(url)

        # 等待页面加载完成
        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
        except TimeoutException:
            pass

        time.sleep(0.5)  # 额外等待JS渲染

        # 获取内容区域HTML - 尝试多种选择器
        content_div = None
        html_content = None

        selectors = ['.content', '.tui-editor-contents', '#content', 'article', '.markdown-body']
        for selector in selectors:
            try:
                content_div = driver.find_element(By.CSS_SELECTOR, selector)
                html_content = content_div.get_attribute('innerHTML')
                if html_content and len(html_content) > 100:
                    break
            except NoSuchElementException:
                continue

        if not html_content or len(html_content) < 100:
            return None, None

        soup = BeautifulSoup(html_content, 'html.parser')

        # 提取标题
        title = None
        for tag in ['h1', 'h2', 'h3']:
            h = soup.find(tag)
            if h:
                title = h.get_text(strip=True)
                break

        if not title:
            page_title = driver.title
            if ' - ' in page_title:
                title = page_title.split(' - ')[0]
            else:
                return None, None

        # 检查内容是否有效
        text = soup.get_text()
        if len(text) < 200:
            return None, None

        # 转换为Markdown
        md_content = html_to_markdown(soup, title)
        return title, md_content

    except Exception as e:
        print(f"  [Error] doc_id={doc_id}: {e}")
        return None, None


def html_to_markdown(content_div, title: str) -> str:
    """将HTML内容转换为Markdown"""
    md_lines = [f"### {title}\n"]

    def process_element(element, depth=0):
        """递归处理元素"""
        if not hasattr(element, 'name') or not element.name:
            return

        # 跳过搜索面板等非内容区域
        if element.name == 'div' and element.get('class') and 'search' in ' '.join(element.get('class', [])):
            return

        if element.name in ['h1', 'h2', 'h3', 'h4', 'h5']:
            text = element.get_text(strip=True)
            if text and text != title:
                md_lines.append(f"\n**{text}**\n")
            return

        if element.name == 'p':
            text = process_inline_elements(element)
            if text.strip():
                md_lines.append(f"\n{text}\n")
            return

        if element.name == 'pre':
            code = element.get_text()
            if code.strip():
                md_lines.append(f"\n```\n{code.strip()}\n```\n")
            return

        if element.name == 'table':
            md_table = convert_table_to_markdown(element)
            if md_table:
                md_lines.append(f"\n{md_table}\n")
            return

        if element.name == 'ul':
            for li in element.find_all('li', recursive=False):
                text = li.get_text(strip=True)
                if text:
                    md_lines.append(f"- {text}")
            md_lines.append("")  # 添加空行
            return

        if element.name == 'ol':
            for i, li in enumerate(element.find_all('li', recursive=False), 1):
                text = li.get_text(strip=True)
                if text:
                    md_lines.append(f"{i}. {text}")
            md_lines.append("")  # 添加空行
            return

        if element.name == 'blockquote':
            text = element.get_text(strip=True)
            if text:
                md_lines.append(f"\n> {text}\n")
            return

        # 对于容器元素（div等），递归处理子元素
        if element.name in ['div', 'section', 'article', 'span']:
            for child in element.children:
                process_element(child, depth + 1)

    # 遍历所有直接子元素并处理
    for element in content_div.children:
        process_element(element)

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


def traverse_mapping(mapping: Dict, path: List[str] = None) -> List[Tuple[str, str, str, str]]:
    """遍历层次化映射，返回 (路径, 名称, doc_id, api接口名) 列表"""
    if path is None:
        path = []

    results = []

    for name, info in mapping.items():
        current_path = path + [name]

        if 'children' in info:
            # 递归处理子节点
            results.extend(traverse_mapping(info['children'], current_path))
        else:
            # 叶子节点
            doc_id = info.get('doc_id', '')
            api = info.get('api', '')
            results.append(('/'.join(current_path), name, doc_id, api))

    return results


def generate_markdown_doc(results: List[Tuple[str, str, str, str, str]], output_file: Path, mapping: Dict):
    """生成Markdown文档"""
    print(f"\n生成文档: {output_file}")

    # 按路径组织
    organized = {}
    for path, name, doc_id, api, content in results:
        parts = path.split('/')
        if len(parts) >= 2:
            category = '/'.join(parts[:-1])
        else:
            category = parts[0]

        if category not in organized:
            organized[category] = []
        organized[category].append((name, doc_id, api, content))

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
    for category in sorted(organized.keys()):
        count = len(organized[category])
        anchor = category.replace('/', '_').replace(' ', '_')
        doc_lines.append(f"- [{category}](#{anchor}) ({count}个接口)")

    doc_lines.append("")
    doc_lines.append("---")
    doc_lines.append("")

    # 添加各分类内容
    for category in sorted(organized.keys()):
        anchor = category.replace('/', '_').replace(' ', '_')
        doc_lines.append(f'<a id="{anchor}"></a>')
        doc_lines.append(f"## {category}")
        doc_lines.append("")
        doc_lines.append("---")
        doc_lines.append("")

        for name, doc_id, api, content in sorted(organized[category]):
            doc_lines.append(f"<!-- doc_id: {doc_id}, api: {api} -->")
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
    print("  Tushare API 文档爬虫 - Selenium版本")
    print("=" * 60)

    # 加载映射
    with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
        mapping = json.load(f)

    print(f"\n加载了映射文件: {MAPPING_FILE}")

    # 遍历获取所有叶子节点
    items = traverse_mapping(mapping)
    print(f"发现 {len(items)} 个API文档页面")

    # 初始化Selenium
    print("\n初始化浏览器...")
    driver = setup_driver()

    # 爬取内容
    results = []

    try:
        for i, (path, name, doc_id, api) in enumerate(items, 1):
            if not doc_id:
                # 生成占位内容
                placeholder = f"### {name}\n\n*待补充*\n\n"
                results.append((path, name, doc_id, api, placeholder))
                print(f"  [{i}/{len(items)}] 跳过: {name} (无doc_id)")
                continue

            print(f"  [{i}/{len(items)}] 爬取: {name} (doc_id={doc_id})")

            title, content = fetch_page_content(driver, doc_id)

            if title and content:
                results.append((path, name, doc_id, api, content))
                print(f"    -> 成功: {title}")
            else:
                # 生成占位内容
                placeholder = f"### {name}\n\n*待补充*\n\n**接口**: `{api}`\n\n**doc_id**: {doc_id}\n"
                results.append((path, name, doc_id, api, placeholder))
                print(f"    -> 使用占位符")

            time.sleep(0.2)

        generate_markdown_doc(results, OUTPUT_FILE, mapping)

    finally:
        driver.quit()

    print("\n" + "=" * 60)
    print("  完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
