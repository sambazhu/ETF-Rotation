#!/usr/bin/env python3
"""
修复缓存中缺失的份额(share_total)和净值(nav)数据。

用途：
  python fix_missing_share_data.py

流程：
  1. 读取现有缓存文件
  2. 批量获取指定时间段内的份额数据
  3. 合并到每只ETF的日线数据中
  4. 重新写入缓存
"""

from __future__ import annotations

import sys
import os
import pandas as pd

# 确保项目根目录在path中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.data_fetcher import DataFetcher
from config.etf_pool import get_all_etf_codes

def fix_cache():
    print("=== 修复ETF缓存数据: 添加份额和净值 ===\n")

    # 初始化fetcher（使用AKShare）
    fetcher = DataFetcher(
        data_source="akshare",
        fallback_to_mock=False,
        api_delay=1.0
    )

    # 1. 获取所有ETF代码
    all_codes = get_all_etf_codes()
    print(f"共 {len(all_codes)} 只ETF")

    # 2. 批量获取完整数据（包含净值）
    print("\n步骤1: 从缓存/网络获取日线+净值数据...")
    all_etf_data = fetcher.fetch_all_etf_data(
        start_date="2023-01-01",
        end_date="2025-12-31",
        codes=all_codes,
        include_nav=True  # 会自动获取并合并净值
    )

    # 3. 获取份额数据
    print("\n步骤2: 批量获取份额数据...")
    shares_df = fetcher.fetch_shares_for_period(
        start_date="2023-01-01",
        end_date="2025-12-31",
        codes=all_codes
    )

    if shares_df.empty:
        print("[警告] 份额数据为空，跳过合并")
        return

    print(f"  获取到 {len(shares_df)} 条份额记录")
    print(f"  覆盖 {shares_df['code'].nunique()} 只ETF")
    print(f"  日期范围: {shares_df['date'].min()} ~ {shares_df['date'].max()}")

    # 4. 合并份额到每只ETF
    print("\n步骤3: 合并份额数据到每只ETF...")
    merged_data = fetcher.merge_shares_into_daily(all_etf_data, shares_df)

    # 5. 更新缓存
    print("\n步骤4: 重新写入缓存...")
    cache = fetcher.cache

    for i, (code, df) in enumerate(merged_data.items(), 1):
        pct = (i / len(merged_data)) * 100
        print(f"\r  [{i}/{len(merged_data)}] {code} ...", end="", flush=True)

        # 检查字段
        has_share = "share_total" in df.columns
        has_nav = "nav" in df.columns
        has_prem = "premium_rate" in df.columns

        share_valid = df["share_total"].notna().sum() if has_share else 0
        nav_valid = df["nav"].notna().sum() if has_nav else 0

        # 重新写入缓存（覆盖旧文件）
        cache.write("etf_daily", code, df)

    print(f"\r  完成! 100% ({len(merged_data)}/{len(merged_data)})")

    # 6. 验证修复结果
    print("\n\n=== 验证修复结果 ===")
    samples = ["510300", "159790", "512100"]

    for code in samples:
        cached = cache.read("etf_daily", code)
        if cached is not None and not cached.empty:
            cols = cached.columns.tolist()
            print(f"\n{code}:")
            print(f"  列: {cols}")

            if "share_total" in cols:
                valid = cached["share_total"].notna().sum()
                print(f"  share_total: 有 | 有效值 {valid}/{len(cached)}")
            else:
                print(f"  share_total: 缺失!")

            if "nav" in cols:
                valid = cached["nav"].notna().sum()
                print(f"  nav: 有 | 有效值 {valid}/{len(cached)}")
            else:
                print(f"  nav: 缺失!")

            if "premium_rate" in cols:
                valid = cached["premium_rate"].notna().sum()
                print(f"  premium_rate: 有 | 有效值 {valid}/{len(cached)}")
            else:
                print(f"  premium_rate: 缺失!")
        else:
            print(f"{code}: 缓存读取失败")

    print("\n=== 修复完成 ===")
    print("\n下一步:")
    print("  1. 运行 check_factors.py 验证因子计算是否正常")
    print("  2. 运行回测验证完整流程")

if __name__ == "__main__":
    fix_cache()
