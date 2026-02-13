# Tushare API 完整参考文档

> 本文档由爬虫自动生成
> 来源: https://tushare.pro/document/2
> 说明: 部分页面需要登录访问，本文档仅收录公开可访问的API文档

---

## 目录

- [股票数据/基础数据](#股票数据基础数据)
  - [股票列表 (stock_basic)](#股票列表-stock_basic)
- [股票数据/行情数据](#股票数据行情数据)
  - [A股日线行情 (daily)](#a股日线行情-daily)
  - [每日指标 (daily_basic)](#每日指标-daily_basic)
- [股票数据/参考数据](#股票数据参考数据)
  - [大宗交易 (block_trade)](#大宗交易-block_trade)
- [ETF专题](#etf专题)
  - [ETF份额规模 (etf_share_size)](#etf份额规模-etf_share_size)
- [债券专题](#债券专题)
  - [柜台流通式债券报价 (bc_otcqt)](#柜台流通式债券报价-bc_otcqt)
- [打板专题](#打板专题)
  - [东方财富热榜 (dc_hot)](#东方财富热榜-dc_hot)

---

## 代码格式规范

Tushare代码格式：`代码.交易所后缀`

| 交易所 | 后缀 | 示例 |
|-------|-----|------|
| 上海证券交易所 | .SH | 600000.SH (股票) / 000001.SH (指数) |
| 深圳证券交易所 | .SZ | 000001.SZ (股票) / 399005.SZ (指数) |
| 北京证券交易所 | .BJ | 8XXXXX.BJ |
| 香港证券交易所 | .HK | 00001.HK |

---

## 积分说明

- 免费接口：注册即可使用
- 120分：基础行情数据
- 500分：指数成分数据
- 2000分：基础信息、每日指标
- 5000分：技术因子数据
- 8000分：ETF份额规模数据、东方财富热榜

积分获取方式：https://tushare.pro/document/1?doc_id=13

---

<a id="股票数据基础数据"></a>
## 股票数据/基础数据

---

### 股票列表 (stock_basic)

**接口**: `stock_basic`

**描述**: 获取基础信息数据，包括股票代码、名称、上市日期、退市日期等

**权限**: 2000积分起。此接口是基础信息，调取一次就可以拉取完，建议保存到本地存储后使用

#### 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | TS股票代码 |
| name | str | N | 名称 |
| market | str | N | 市场类别（主板/创业板/科创板/CDR/北交所） |
| list_status | str | N | 上市状态 L上市 D退市 P暂停上市 G过会未交易，默认是L |
| exchange | str | N | 交易所 SSE上交所 SZSE深交所 BSE北交所 |
| is_hs | str | N | 是否沪深港通标的，N否 H沪股通 S深股通 |

#### 输出参数

| 名称 | 类型 | 描述 |
| --- | --- | --- |
| ts_code | str | TS代码 |
| symbol | str | 股票代码 |
| name | str | 股票名称 |
| area | str | 地域 |
| industry | str | 所属行业 |
| fullname | str | 股票全称 |
| enname | str | 英文全称 |
| cnspell | str | 拼音缩写 |
| market | str | 市场类型（主板/创业板/科创板/CDR） |
| exchange | str | 交易所代码 |
| curr_type | str | 交易货币 |
| list_status | str | 上市状态 |
| list_date | str | 上市日期 |
| delist_date | str | 退市日期 |
| is_hs | str | 是否沪深港通标的 |
| act_name | str | 实控人名称 |
| act_ent_type | str | 实控人企业性质 |

#### 接口示例

```python
pro = ts.pro_api()

# 查询当前所有正常上市交易的股票列表
data = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')

# 或者
data = pro.query('stock_basic', exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
```

#### 数据样例

```
    ts_code     symbol     name     area industry    list_date
0     000001.SZ  000001  平安银行   深圳       银行  19910403
1     000002.SZ  000002   万科A   深圳     全国地产  19910129
2     000004.SZ  000004  国农科技   深圳     生物制药  19910114
3     000005.SZ  000005  世纪星源   深圳     房产服务  19901210
4     000006.SZ  000006  深振业A   深圳     区域地产  19920427
```

---

<a id="股票数据行情数据"></a>
## 股票数据/行情数据

---

### A股日线行情 (daily)

**接口**: `daily`

**描述**: 获取股票行情数据（未复权），停牌期间不提供数据

**更新时间**: 交易日每天15点～16点之间入库

**调取说明**: 基础积分每分钟内可调取500次，每次6000条数据

#### 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | 股票代码（支持多个股票同时提取，逗号分隔） |
| trade_date | str | N | 交易日期（YYYYMMDD） |
| start_date | str | N | 开始日期(YYYYMMDD) |
| end_date | str | N | 结束日期(YYYYMMDD) |

#### 输出参数

| 名称 | 类型 | 描述 |
| --- | --- | --- |
| ts_code | str | 股票代码 |
| trade_date | str | 交易日期 |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| pre_close | float | 昨收价【除权价】 |
| change | float | 涨跌额 |
| pct_chg | float | 涨跌幅【基于除权后的昨收计算】 |
| vol | float | 成交量（手） |
| amount | float | 成交额（千元） |

#### 接口示例

```python
pro = ts.pro_api()

# 单个股票
df = pro.daily(ts_code='000001.SZ', start_date='20180701', end_date='20180718')

# 多个股票
df = pro.daily(ts_code='000001.SZ,600000.SH', start_date='20180701', end_date='20180718')

# 按日期取历史某一天的全部数据
df = pro.daily(trade_date='20180810')
```

#### 数据样例

```
 ts_code     trade_date  open  high   low  close  pre_close  change  pct_chg  vol        amount
0  000001.SZ   20180718  8.75  8.85  8.69   8.70       8.72   -0.02    -0.23   525152.77   460697.377
1  000001.SZ   20180717  8.74  8.75  8.66   8.72       8.73   -0.01    -0.11   375356.33   326396.994
2  000001.SZ   20180716  8.85  8.90  8.69   8.73       8.88   -0.15    -1.69   689845.58   603427.713
```

---

### 每日指标 (daily_basic)

**接口**: `daily_basic`

**描述**: 获取全部股票每日重要的基本面指标，可用于选股分析、报表展示等

**更新时间**: 交易日每日15点～17点之间

**积分**: 至少2000积分才可以调取，5000积分无总量限制

#### 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | 股票代码（二选一） |
| trade_date | str | N | 交易日期（二选一） |
| start_date | str | N | 开始日期(YYYYMMDD) |
| end_date | str | N | 结束日期(YYYYMMDD) |

#### 输出参数

| 名称 | 类型 | 描述 |
| --- | --- | --- |
| ts_code | str | TS股票代码 |
| trade_date | str | 交易日期 |
| close | float | 当日收盘价 |
| turnover_rate | float | 换手率（%） |
| turnover_rate_f | float | 换手率（自由流通股） |
| volume_ratio | float | 量比 |
| pe | float | 市盈率（总市值/净利润，亏损的PE为空） |
| pe_ttm | float | 市盈率（TTM，亏损的PE为空） |
| pb | float | 市净率（总市值/净资产） |
| ps | float | 市销率 |
| ps_ttm | float | 市销率（TTM） |
| dv_ratio | float | 股息率（%） |
| dv_ttm | float | 股息率（TTM）（%） |
| total_share | float | 总股本（万股） |
| float_share | float | 流通股本（万股） |
| free_share | float | 自由流通股本（万） |
| total_mv | float | 总市值（万元） |
| circ_mv | float | 流通市值（万元） |

#### 接口示例

```python
pro = ts.pro_api()

df = pro.daily_basic(ts_code='', trade_date='20180726', fields='ts_code,trade_date,turnover_rate,volume_ratio,pe,pb')
```

---

<a id="股票数据参考数据"></a>
## 股票数据/参考数据

---

### 大宗交易 (block_trade)

**接口**: `block_trade`

**描述**: 大宗交易数据

**限量**: 单次最大1000条，总量不限制

**积分**: 300积分可调取

#### 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | TS代码（股票代码和日期至少输入一个参数） |
| trade_date | str | N | 交易日期（格式：YYYYMMDD） |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

#### 输出参数

| 名称 | 类型 | 描述 |
| --- | --- | --- |
| ts_code | str | TS代码 |
| trade_date | str | 交易日历 |
| price | float | 成交价 |
| vol | float | 成交量（万股） |
| amount | float | 成交金额 |
| buyer | str | 买方营业部 |
| seller | str | 卖方营业部 |

#### 接口示例

```python
pro = ts.pro_api()

df = pro.block_trade(trade_date='20181227')
```

---

<a id="etf专题"></a>
## ETF专题

---

### ETF份额规模 (etf_share_size)

**接口**: `etf_share_size`

**描述**: 获取沪深ETF每日份额和规模数据，能体现规模份额的变化，掌握ETF资金动向，同时提供每日净值和收盘价

**限量**: 单次最大5000条，可根据代码或日期循环提取

**积分**: 需要8000积分可以调取

#### 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | 基金代码（可从ETF基础信息接口提取） |
| trade_date | str | N | 交易日期（YYYYMMDD格式） |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |
| exchange | str | N | 交易所（SSE上交所 SZSE深交所） |

#### 输出参数

| 名称 | 类型 | 描述 |
| --- | --- | --- |
| trade_date | str | 交易日期 |
| ts_code | str | ETF代码 |
| etf_name | str | 基金名称 |
| total_share | float | 总份额（万份） |
| total_size | float | 总规模（万元） |
| nav | float | 基金份额净值(元) |
| close | float | 收盘价（元） |
| exchange | str | 交易所（SSE/SZSE/BSE） |

#### 接口示例

```python
# 获取"沪深300ETF华夏"ETF2025年以来每个交易日的份额和规模情况
df = pro.etf_share_size(ts_code='510330.SH', start_date='20250101', end_date='20251224')

# 获取2025年12月24日上交所的所有ETF份额和规模情况
df = pro.etf_share_size(trade_date='20251224', exchange='SSE')
```

#### 数据样例

```
    trade_date    ts_code       etf_name  total_share    total_size exchange
0     20251224  510330.SH  沪深300ETF华夏   4741854.98  2.287898e+07      SSE
1     20251222  510330.SH  沪深300ETF华夏   4746894.98  2.279127e+07      SSE
2     20251219  510330.SH  沪深300ETF华夏   4756974.98  2.262512e+07      SSE
```

---

<a id="债券专题"></a>
## 债券专题

---

### 柜台流通式债券报价 (bc_otcqt)

**接口**: `bc_otcqt`

**描述**: 柜台流通式债券报价

**限量**: 单次最大2000条，可多次提取

**积分**: 用户需要至少500积分可以试用调取

#### 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| trade_date | str | N | 交易日期(YYYYMMDD格式) |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |
| ts_code | str | N | TS代码 |
| bank | str | N | 报价机构 |

#### 输出参数

| 名称 | 类型 | 描述 |
| --- | --- | --- |
| trade_date | str | 报价日期 |
| qt_time | str | 报价时间 |
| bank | str | 报价机构 |
| ts_code | str | 债券编码 |
| name | str | 债券简称 |
| maturity | str | 期限 |
| remain_maturity | str | 剩余期限 |
| bond_type | str | 债券类型 |
| coupon_rate | float | 票面利率（%） |
| buy_price | float | 投资者买入全价 |
| sell_price | float | 投资者卖出全价 |
| buy_yield | float | 投资者买入到期收益率（%） |
| sell_yield | float | 投资者卖出到期收益率（%） |

#### 接口示例

```python
pro = ts.pro_api(your_token)

# 柜台流通式债券报价
df = pro.bc_otcqt(start_date='20240325', end_date='20240329', ts_code='200013.BC',
                  fields='trade_date,qt_time,bank,ts_code,name,remain_maturity,buy_yield,sell_yield')
```

---

<a id="打板专题"></a>
## 打板专题

---

### 东方财富热榜 (dc_hot)

**接口**: `dc_hot`

**描述**: 获取东方财富App热榜数据，包括A股市场、ETF基金、港股市场、美股市场等

**更新频率**: 每日盘中提取4次，收盘后4次，最晚22点提取一次

**限量**: 单次最大2000条

**积分**: 用户积8000积分可调取使用

**注意**: 本接口只限个人学习和研究使用

#### 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| trade_date | str | N | 交易日期 |
| ts_code | str | N | TS代码 |
| market | str | N | 类型(A股市场、ETF基金、港股市场、美股市场) |
| hot_type | str | N | 热点类型(人气榜、飙升榜) |
| is_new | str | N | 是否最新（默认Y，N为盘中和盘后阶段采集） |

#### 输出参数

| 名称 | 类型 | 描述 |
| --- | --- | --- |
| trade_date | str | 交易日期 |
| data_type | str | 数据类型 |
| ts_code | str | 股票代码 |
| ts_name | str | 股票名称 |
| rank | int | 排行或者热度 |
| pct_change | float | 涨跌幅% |
| current_price | float | 当前价 |
| rank_time | str | 排行榜获取时间 |

#### 接口示例

```python
# 获取查询月份券商金股
df = pro.dc_hot(trade_date='20240415', market='A股市场', hot_type='人气榜',
                fields='ts_code,ts_name,rank')
```

#### 数据样例

```
  ts_code   ts_name  rank
0   601099.SH     太平洋     1
1   601995.SH    中金公司     2
2   002235.SZ    安妮股份     3
3   601136.SH    首创证券     4
4   600127.SH    金健米业     5
```

---

## 本项目使用的API

| 用途 | 接口 | 积分要求 |
|-----|-----|---------|
| ETF日线行情 | `pro.fund_daily()` | 120分 |
| ETF份额数据 | `pro.etf_share_size()` | 8000分 |
| 基金净值 | `pro.fund_nav()` | 120分 |
| 交易日历 | `pro.trade_cal()` | 免费 |
| 股票日线 | `pro.daily()` | 120分 |
| 每日指标 | `pro.daily_basic()` | 2000分 |

---

## 字段映射说明

### 成交量/成交额单位转换

| Tushare单位 | 实际单位 | 转换系数 |
|------------|---------|---------|
| 手 | 股 | ×100 |
| 千元 | 元 | ×1000 |
| 万元 | 元 | ×10000 |
| 万份 | 份 | ×10000 |

---

*文档生成时间: 2026-02-13*
