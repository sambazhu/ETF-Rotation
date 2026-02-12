#!/usr/bin/env python3
"""
检查并修复缓存数据完整性。

用途：
  python check_and_fix_cache.py

可选参数:
  --dry-run      只检查，不修复
  --force        强制重新获取所有数据
  --no-shares    不获取份额数据（仅修复净值）
"""

from __future__ import annotations

import sys
import os
import argparse
from typing import Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from data.data_fetcher import DataFetcher
from data.cache_manager import CacheManager
from config.etf_pool import get_all_etf_codes


def inspect_cache(codes: list) -> dict:
    """检查缓存完整性。"""
    cache = CacheManager()
    results = {
        "total": len(codes),
        "with_share": 0,
        "with_nav": 0,
        "with_premium": 0,
        "details": {},
    }

    for code in codes:
        df = cache.read("etf_daily", code)
        if df is None or df.empty:
            results["details"][code] = {"exists": False}
            continue

        has_share = "share_total" in df.columns and df["share_total"].notna().sum() > 0
        has_nav = "nav" in df.columns and df["nav"].notna().sum() > 0
        has_prem = "premium_rate" in df.columns and df["premium_rate"].notna().sum() > 0

        if has_share:
            results["with_share"] += 1
        if has_nav:
            results["with_nav"] += 1
        if has_prem:
            results["with_premium"] += 1

        results["details"][code] = {
            "exists": True,
            "rows": len(df),
            "share_total": has_share,
            "nav": has_nav,
            "premium_rate": has_prem,
            "date_range": f"{df['date'].min()} ~ {df['date'].max()}",
        }

    return results


def show_report(results: dict):
    """显示检查报告。"""
    print("\n" + "=" * 60)
    print("  缓存数据完整性检查")
    print("=" * 60)
    print(f"\n总计: {results['total']} 只ETF")
    print(f"  包含份额数据: {results['with_share']}/{results['total']}")
    print(f"  包含净值数据: {results['with_nav']}/{results['total']}")
    print(f"  包含溢价率: {results['with_premium']}/{results['total']}")

    # 详细列表
    print("\n详细清单:")
    for code, detail in results["details"].items():
        if not detail["exists"]:
            print(f"  {code}: [X] 缓存缺失")
            continue

        flags = []
        flags.append("[share]" if detail["share_total"] else "[no-share]")
        flags.append("[nav]" if detail["nav"] else "[no-nav]")
        flags.append("[prem]" if detail["premium_rate"] else "[no-prem]")

        print(f"  {code}: {detail['rows']} rows [{detail['date_range']}] {' '.join(flags)}")

    # 需要修复的列表
    need_share = [
        code for code, d in results["details"].items()
        if d.get("exists") and not d.get("share_total")
    ]
    need_nav = [
        code for code, d in results["details"].items()
        if d.get("exists") and not d.get("nav")
    ]

    print(f"\n缺失份额数据: {len(need_share)} 只")
    if need_share:
        print(f"  {', '.join(need_share[:10])}" + ("..." if len(need_share) > 10 else ""))

    print(f"缺失净值数据: {len(need_nav)} 只")
    if need_nav:
        print(f"  {', '.join(need_nav[:10])}" + ("..." if len(need_nav) > 10 else ""))


def fix_cache(fetcher: DataFetcher, codes: list, skip_shares: bool = False):
    """修复缓存数据。"""
    print("\n" + "=" * 60)
    print("  开始修复缓存数据")
    print("=" * 60)

    # 1. 获取完整日线+净值
    print("\n步骤1: 获取日线行情和净值数据...")
    all_data = fetcher.fetch_all_etf_data(
        start_date="2023-01-01",
        end_date="2025-12-31",
        codes=codes,
        include_nav=True
    )

    # 2. 获取份额数据
    if not skip_shares:
        print("\n步骤2: 获取份额数据...")
        shares_df = fetcher.fetch_shares_for_period(
            start_date="2023-01-01",
            end_date="2025-12-31",
            codes=codes
        )

        if not shares_df.empty:
            print(f"  获取到 {len(shares_df)} 条份额记录")
            all_data = fetcher.merge_shares_into_daily(all_data, shares_df)
        else:
            print("  [警告] 份额数据为空，跳过合并")
    else:
        print("\n步骤2: 跳过份额数据获取")

    # 3. 写入缓存
    print("\n步骤3: 写入缓存...")
    cache = fetcher.cache
    total = len(all_data)

    for i, (code, df) in enumerate(all_data.items(), 1):
        pct = (i / total) * 100
        print(f"\r  [{i}/{total}] {code} ...", end="", flush=True)

        # 验证字段
        has_share = "share_total" in df.columns
        has_nav = "nav" in df.columns
        has_prem = "premium_rate" in df.columns

        cache.write("etf_daily", code, df)

    print(f"\r  完成! 100% ({total}/{total})")


def main():
    parser = argparse.ArgumentParser(description="检查并修复缓存数据")
    parser.add_argument("--dry-run", action="store_true", help="只检查，不修复")
    parser.add_argument("--force", action="store_true", help="强制重新获取所有数据")
    parser.add_argument("--no-shares", action="store_true", help="不获取份额数据")
    args = parser.parse_args()

    codes = get_all_etf_codes()
    print(f"检查 {len(codes)} 只ETF...")

    results = inspect_cache(codes)
    show_report(results)

    # 判断是否需要修复
    need_fix = False
    if args.force:
        need_fix = True
        print("\n[提示] --force 标志: 将重新获取所有数据")
    else:
        missing_share = results["total"] - results["with_share"]
        missing_nav = results["total"] - results["with_nav"]
        if missing_share > 0 or missing_nav > 0:
            need_fix = True

    if args.dry_run:
        print("\n[DRY RUN] 跳过修复")
        return

    if not need_fix:
        print("\n✅ 缓存数据完整，无需修复")
        return

    # 自动确认修复（不交互）
    print("\n[自动] 检测到缺失数据，开始修复...")

    # 优先使用Tushare（配置文件中已有token）
    data_source = "tushare"

    fetcher = DataFetcher(
        data_source=data_source,
        fallback_to_mock=False,
        api_delay=0.5  # Tushare速度较快
    )

    fix_cache(fetcher, codes, skip_shares=args.no_shares)

    # 重新检查
    print("\n重新检查修复结果...")
    results2 = inspect_cache(codes)
    show_report(results2)


if __name__ == "__main__":
    main()
