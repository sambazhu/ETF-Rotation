# 基金净值 (fund_nav)

> 分类: 公募基金
> 来源: Tushare Pro 文档
> 积分要求: 120分

---

## 接口说明

获取公募基金净值数据，包括单位净值和累计净值。

**数据更新时间**: 每日盘后

---

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | 基金代码（如 510300.SH） |
| trade_date | str | N | 交易日期（YYYYMMDD格式） |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

---

## 输出参数

| 名称 | 类型 | 描述 |
| --- | --- | --- |
| ts_code | str | 基金代码 |
| ann_date | str | 公告日期 |
| nav_date | str | 净值日期 |
| unit_nav | float | 单位净值(元) |
| accum_nav | float | 累计净值(元) |
| accum_div | float | 累计分红(元) |
| net_asset | float | 资产净值(元) |
| total_netasset | float | 合计资产净值(元) |
| adj_nav | float | 复权净值(元) |

---

## 调用示例

```python
import tushare as ts

pro = ts.pro_api('your_token')

# 获取ETF净值数据
df = pro.fund_nav(
    ts_code='510300.SH',
    start_date='20240101',
    end_date='20241231'
)
```

---

## 数据示例

```
     ts_code  ann_date  nav_date  unit_nav  accum_nav  accum_div    net_asset  total_netasset
0  510300.SH  20241224  20241224     3.992      4.823       0.83  18923456789    18923456789.0
1  510300.SH  20241223  20241223     3.976      4.807       0.83  18856723456    18856723456.0
```

---

## 本项目使用

净值数据用于计算ETF溢价率：

```python
# 溢价率 = (收盘价 - 净值) / 净值
premium_rate = (close - nav) / nav
```

---

## 字段说明

- **单位净值(unit_nav)**: 每份基金单位的净资产价值
- **累计净值(accum_nav)**: 单位净值 + 历史分红
- **复权净值(adj_nav)**: 考虑分红再投资的净值
