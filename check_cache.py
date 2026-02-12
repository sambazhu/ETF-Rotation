import pandas as pd
import os

samples = ['159790.csv', '510300.csv', '512100.csv']
print('检查3个ETF样本:')

results = {}
for f in samples:
    path = os.path.join('data/cache/etf_daily', f)
    if os.path.exists(path):
        df = pd.read_csv(path)
        cols = df.columns.tolist()
        has_share = 'share_total' in cols
        print(f'{f}: share_total={has_share}')
        print(f'  列: {cols}')
        if has_share:
            valid_count = df['share_total'].notna().sum()
            print(f'  有效值: {valid_count}/{len(df)}')
    else:
        print(f'{f}: 文件不存在')
