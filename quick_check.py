#!/usr/bin/env python3
"""快速验证因子计算。"""

import sys
sys.path.insert(0, '.')

import pandas as pd
from data.data_fetcher import DataFetcher
from data.data_processor import DataProcessor

fetcher = DataFetcher(data_source='tushare', fallback_to_mock=False)
result = fetcher.fetch_etf_daily('510300', '2023-01-01', '2024-12-31')

print('=== 原始数据 ===')
print('行数:', len(result.data))
print('列:', result.data.columns.tolist())

if 'share_total' in result.data.columns:
    print('share_total有效值:', int(result.data['share_total'].notna().sum()))
if 'nav' in result.data.columns:
    print('nav有效值:', int(result.data['nav'].notna().sum()))

processed = DataProcessor.process(result.data)

print('\n=== 处理后因子 ===')
for col in ['mfi', 'mfa', 'pdi', 'cmc', 'mfi_z', 'mfa_z']:
    if col in processed.columns:
        valid = int(processed[col].notna().sum())
        print(f'{col}: {valid}/{len(processed)}')

        # 显示部分值
        if valid > 0:
            sample = processed[col].dropna().head(3).tolist()
            print(f'  样本: {sample}')
