# ETF份额规模 (etf_share_size)

> 分类: ETF专题
> 来源: Tushare Pro 文档
> 积分要求: 8000分

---

## 接口说明

获取沪深ETF每日份额和规模数据，能体现规模份额的变化，掌握ETF资金动向，同时提供每日净值和收盘价。

**数据更新时间**: 每日19点后（涉及海外的ETF数据更新会晚一些）

**限量**: 单次最大5000条，可根据代码或日期循环提取

---

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | 基金代码（可从ETF基础信息接口提取，如 510300.SH） |
| trade_date | str | N | 交易日期（YYYYMMDD格式） |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |
| exchange | str | N | 交易所（SSE上交所 SZSE深交所） |

---

## 输出参数

| 名称 | 类型 | 描述 |
| --- | --- | --- |
| trade_date | str | 交易日期 |
| ts_code | str | ETF代码 |
| etf_name | str | 基金名称 |
| total_share | float | 总份额（万份） |
| total_size | float | 总规模（万元） |
| nav | float | 基金份额净值（元） |
| close | float | 收盘价（元） |
| exchange | str | 交易所（SSE/SZSE/BSE） |

---

## 调用示例

```python
import tushare as ts

pro = ts.pro_api('your_token')

# 获取单只ETF的份额数据
df = pro.etf_share_size(
    ts_code='510300.SH',
    start_date='20240101',
    end_date='20241231'
)

# 获取某日某交易所所有ETF份额
df = pro.etf_share_size(
    trade_date='20241224',
    exchange='SSE'
)
```

---

## 数据示例

```
   trade_date    ts_code      etf_name  total_share    total_size exchange
0   20241224  510300.SH   沪深300ETF   4741854.98  2.287898e+07      SSE
1   20241223  510300.SH   沪深300ETF   4746894.98  2.279127e+07      SSE
2   20241220  510300.SH   沪深300ETF   4756974.98  2.262512e+07      SSE
```

---

## 本项目使用

在 `data/data_sources.py` 中使用此接口获取ETF份额数据：

```python
def fetch_etf_shares_tushare(codes, start_date, end_date):
    """通过 Tushare etf_share_size 获取ETF份额数据。"""
    import tushare as ts
    pro = ts.pro_api(TUSHARE_TOKEN)

    # 转换代码格式: 510300 -> 510300.SH
    ts_codes = [f"{code}.SH" if code.startswith('5') else f"{code}.SZ"
                for code in codes]

    df = pro.etf_share_size(
        ts_code=','.join(ts_codes),
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
| total_share | share_total | 份额（万份） |
| nav | nav | 净值 |
| close | close | 收盘价 |
