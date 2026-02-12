import sys
sys.path.insert(0, '.')
import pandas as pd
from data.data_fetcher import DataFetcher
from data.data_processor import DataProcessor

fetcher = DataFetcher(data_source='akshare', fallback_to_mock=True)
result = fetcher.fetch_etf_daily('510300', '2023-01-01', '2024-12-31')

print('原始数据行数:', len(result.data))
print('原始列:', result.data.columns.tolist())

print('\n检查是否包含份额:')
if 'share_total' in result.data.columns:
    print('  share_total: 是 | 有值:', result.data['share_total'].notna().sum())
else:
    print('  share_total: 否')

if 'nav' in result.data.columns:
    print('  nav: 是 | 有值:', result.data['nav'].notna().sum())
else:
    print('  nav: 否')

processed = DataProcessor.process(result.data)
print('\n处理后数据行数:', len(processed))

print('\n因子值统计:')
stats = {}
for col in ['mfi', 'mfa', 'pdi', 'cmc', 'premium_rate', 'mfi_z', 'mfa_z', 'pdi_z', 'cmc_z']:
    if col in processed.columns:
        stats[col] = {
            '有效值': processed[col].notna().sum(),
            '均值': float(processed[col].mean()),
            '范围': f"[{processed[col].min():.4f}, {processed[col].max():.4f}]"
        }
    else:
        stats[col] = '缺失'

import json
print(json.dumps(stats, indent=2, ensure_ascii=False))
