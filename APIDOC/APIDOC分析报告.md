# Tushare API 使用分析

## 当前问题：宏观因子为 0 的根本原因

### 1. 缓存数据字段缺失

检查了 `data/cache/etf_daily/*.csv` 文件，发现：
```python
['date', 'code', 'open', 'high', 'low', 'close', 'volume', 'amount']
```
**缺失字段**：
- ❌ `share_total`（份额）→ 无法计算资金流
- ❌ `nav`（净值）→ 缓存中未包含

### 2. 数据源分析

**Tushare API 能获取完整数据**：

| 数据类型 | API 接口 | 字段 | 状态 |
|---------|---------|------|------|
| **ETF日线** | `pro.fund_daily()` | open/high/low/close/vol/amount | ✅ 可用 |
| **份额数据** | `pro.fund_share()` | fd_share（份额） | ✅ 可用 |
| **净值数据** | `pro.fund_nav()` | unit_nav/accum_nav | ✅ 可用 |

**测试结果**：
```python
# ETF日线
df = pro.fund_daily(ts_code='510300.SH', ...)
# 列: ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount']

# 份额
shares = pro.fund_share(ts_code='510300.SH', ...)
# 列: ['ts_code', 'trade_date', 'fd_share']  ← 包含份额

# 净值
nav = pro.fund_nav(ts_code='510300.SH', ...)
# 列: ['ts_code', 'nav_date', 'unit_nav']  ← 包含净值
```

### 3. 问题根源

**DataFetcher 未合并份额和净值到日线中**：

当前 `fetch_etf_daily()` 只返回基础行情数据，没有：
1. 调用 `fetch_etf_shares()` 获取份额
2. 调用 `fetch_etf_nav()` 获取净值
3. 合并这些数据到日线中

**结果**：
- `share_total` 字段缺失 → `net_inflow` = 0
- `nav` 字段缺失 → `premium_rate` 无法计算
- 宏观因子全部为 0

### 4. 解决方案

#### 方案一：修改 DataFetcher.fetch_etf_daily()

在 [data/data_fetcher.py](file://e:\samba_workplace\ETF\data\data_fetcher.py) 中：

```python
def fetch_etf_daily(self, code, start_date, end_date, use_cache=True):
    # ... 现有代码 ...

    # 获取净值并合并
    if include_nav and not df.empty:
        nav_result = self.fetch_etf_nav(code)
        if not nav_result.data.empty:
            nav_df = nav_result.data[['date', 'nav']].copy()
            df = df.merge(nav_df, on='date', how='left')

    # 获取份额数据（需要逐日获取并合并）
    # ... 合并份额逻辑 ...

    return FetchResult(df, ...)
```

#### 方案二：修改 backtest_engine.py

在加载数据后手动合并：

```python
# 获取份额数据（整个回测区间）
shares_data = fetcher.fetch_shares_for_period(start, end, codes)

# 合并到每只ETF的日线中
self.market_data = fetcher.merge_shares_into_daily(
    self.market_data,
    shares_data
)
```

---

## API 文档爬虫建议

### 是否需要？

**建议：需要**，理由如下：

1. **Tushare 文档分散**：接口分布在多个页面（如 [ETF数据](https://tushare.pro/document/2?doc_id=408)）
2. **接口参数复杂**：需要了解字段含义、频率限制、返回格式
3. **调试困难**：当前缺少文档参考，导致数据获取不完整

### 实施建议

#### 1. 创建 APIDOC 目录结构

```
APIDOC/
├── tushare/
│   ├── fund_daily.md      # ETF日线行情
│   ├── fund_share.md      # 基金份额
│   ├── fund_nav.md        # 基金净值
│   ├── fund_basic.md      # 基金列表
│   └── index.md           # 索引
└── akshare/
    └── fund_etf_hist_em.md
```

#### 2. 爬虫实现要点

```python
import requests
from bs4 import BeautifulSoup

def scrape_tushare_api(doc_id):
    url = f"https://tushare.pro/document/2?doc_id={doc_id}"
    # 需要登录认证（Tushare需要登录后才能访问）
    # 可以手动保存为HTML或使用Selenium
    pass
```

**难点**：
- ❗ Tushare 文档需要登录才能访问
- ❗ 需要处理登录态和反爬虫机制

#### 3. 替代方案（推荐）

**手动整理核心 API 文档**：

| 文档类型 | 内容 | 优先级 |
|---------|------|--------|
| **Tushare ETF日线** | 字段说明、调用频率、示例代码 | ⭐⭐⭐ |
| **Tushare 份额数据** | fd_share 含义、更新频率 | ⭐⭐⭐ |
| **Tushare 净值数据** | unit_nav vs accum_nav | ⭐⭐⭐ |
| **字段映射表** | API字段 → 系统字段对照 | ⭐⭐⭐⭐ |

**示例 `fund_daily.md`**：

```markdown
# fund_daily - ETF日线行情

## 接口地址
https://tushare.pro/document/2?doc_id=408

## 调用方法
```python
df = pro.fund_daily(ts_code='510300.SH', start_date='20230101', end_date='20230131')
```

## 参数说明
| 参数 | 类型 | 必选 | 说明 |
|-----|------|-----|------|
| ts_code | str | N | TS代码，如 510300.SH |
| trade_date | str | N | 交易日期 |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

## 返回字段
| 字段 | 类型 | 说明 | 系统字段映射 |
|-----|------|------|-------------|
| ts_code | str | TS代码 | code |
| trade_date | str | 交易日期 | date |
| open | float | 开盘价 | open |
| high | float | 最高价 | high |
| low | float | 最低价 | low |
| close | float | 收盘价 | close |
| vol | float | 成交量（手） | volume |
| amount | float | 成交额（千元） | amount |
| pre_close | float | 昨收价 | - |
| change | float | 涨跌额 | - |
| pct_chg | float | 涨跌幅 | - |
```

---

## 总结

### 当前问题
✅ **确认**：缓存数据缺失 `share_total` 和 `nav`
✅ **原因**：DataFetcher 未合并份额和净值数据
✅ **影响**：宏观因子计算为 0，策略无效

### 解决步骤
1. **修改 DataFetcher.fetch_etf_daily()**：合并净值
2. **修改 backtest_engine.py**：获取并合并份额数据
3. **清理缓存**：`rm -rf data/cache/`
4. **重新回测**：验证因子是否正常

### 关于 API 文档爬虫
✅ **建议实施**：整理 Tushare 核心 API 文档
✅ **优先手动整理**：先整理 `fund_daily`、`fund_share`、`fund_nav`
✅ **后续自动化**：如果文档经常更新，再考虑爬虫方案

需要我帮你修改代码实现数据合并吗？
