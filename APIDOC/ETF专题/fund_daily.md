# ETF日线行情 (fund_daily)

> 分类: ETF专题
> 来源: Tushare Pro 文档
> 积分要求: 120分

---

## 接口说明

获取ETF基金每日行情数据，包括开盘价、最高价、最低价、收盘价、成交量、成交额等。

**数据更新时间**: 每日15点-16点之间入库

**限量**: 单次最大8000行数据

---

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | ETF代码（支持多个同时提取，逗号分隔，如 510300.SH,159915.SZ） |
| trade_date | str | N | 交易日期（YYYYMMDD格式） |
| start_date | str | N | 开始日期(YYYYMMDD) |
| end_date | str | N | 结束日期(YYYYMMDD) |

---

## 输出参数

| 名称 | 类型 | 描述 |
| --- | --- | --- |
| ts_code | str | ETF代码 |
| trade_date | str | 交易日期 |
| pre_close | float | 昨收盘价(元) |
| open | float | 开盘价(元) |
| high | float | 最高价(元) |
| low | float | 最低价(元) |
| close | float | 收盘价(元) |
| change | float | 涨跌额(元) |
| pct_chg | float | 涨跌幅(%) |
| vol | float | 成交量(手) |
| amount | float | 成交额(千元) |

---

## 调用示例

```python
import tushare as ts

pro = ts.pro_api('your_token')

# 获取单只ETF日线数据
df = pro.fund_daily(
    ts_code='510300.SH',
    start_date='20240101',
    end_date='20241231'
)

# 获取多个ETF数据
df = pro.fund_daily(
    ts_code='510300.SH,159915.SZ',
    start_date='20240101',
    end_date='20241231'
)

# 获取某日所有ETF行情
df = pro.fund_daily(trade_date='20241224')
```

---

## 数据示例

```
     ts_code trade_date  pre_close   open   high    low  close  change  pct_chg       vol       amount
0  510300.SH   20241224      3.98   3.97   4.01   3.96   4.00    0.02     0.50  452345.0  180523.456
1  510300.SH   20241223      3.95   3.96   3.99   3.94   3.98    0.03     0.76  389234.0  154823.123
2  510300.SH   20241220      3.92   3.93   3.96   3.91   3.95    0.03     0.77  412567.0  162934.567
```

---

## 本项目使用

在 `data/data_sources.py` 中使用此接口获取ETF日线数据：

```python
def fetch_etf_daily_tushare(code, start_date, end_date):
    """获取ETF日线数据。"""
    import tushare as ts
    pro = ts.pro_api(TUSHARE_TOKEN)

    # 转换代码格式
    ts_code = f"{code}.SH" if code.startswith('5') else f"{code}.SZ"

    df = pro.fund_daily(
        ts_code=ts_code,
        start_date=start_date.replace('-', ''),
        end_date=end_date.replace('-', '')
    )
    return df
```

---

## 字段映射

| Tushare字段 | 系统字段 | 说明 |
|------------|---------|------|
| ts_code | code | 去掉后缀 (.SH/.SZ) |
| trade_date | date | 格式转换为 YYYY-MM-DD |
| open | open | 开盘价 |
| high | high | 最高价 |
| low | low | 最低价 |
| close | close | 收盘价 |
| vol | volume | 成交量(手→股需x100) |
| amount | amount | 成交额(千元→元需x1000) |

---

## 注意事项

1. 成交量单位是"手"，1手=100股
2. 成交额单位是"千元"
3. 代码格式需要带交易所后缀（.SH/.SZ）
4. 停牌期间不提供数据
