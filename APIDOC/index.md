# Tushare API 文档索引

> 本文档由爬虫自动生成，来源：https://tushare.pro/document/2

---

## 目录

### ETF专题

| 文档 | 接口名 | 积分要求 | 说明 |
|-----|-------|---------|------|
| [ETF日线行情](ETF专题/fund_daily.md) | fund_daily | 120分 | ETF日线行情数据 |
| [ETF份额规模](ETF专题/etf_share_size.md) | etf_share_size | 8000分 | ETF每日份额和规模 |
| [ETF复权因子](ETF专题/fund_adj.md) | fund_adj | 120分 | ETF复权因子 |

### 公募基金

| 文档 | 接口名 | 积分要求 | 说明 |
|-----|-------|---------|------|
| [基金净值](公募基金/fund_nav.md) | fund_nav | 120分 | 基金净值数据 |
| [基金规模](公募基金/fund_scale.md) | fund_scale | 120分 | 基金规模数据 |

### 指数专题

| 文档 | 接口名 | 积分要求 | 说明 |
|-----|-------|---------|------|
| [指数基本信息](指数专题/index_basic.md) | index_basic | 120分 | 指数基础信息 |
| [指数成分和权重](指数专题/index_weight.md) | index_weight | 500分 | 指数成分股权重 |
| [申万行业分类](指数专题/index_classify.md) | index_classify | 120分 | 申万行业分类 |

### 股票数据

| 文档 | 接口名 | 积分要求 | 说明 |
|-----|-------|---------|------|
| [股票列表](股票基础/stock_basic.md) | stock_basic | 免费 | 股票基础列表 |
| [交易日历](股票基础/trade_cal.md) | trade_cal | 免费 | 交易日历 |
| [日线行情](股票行情/daily.md) | daily | 120分 | 股票日线行情 |
| [每日指标](股票行情/daily_basic.md) | daily_basic | 120分 | 每日指标 |

### 特色数据

| 文档 | 接口名 | 积分要求 | 说明 |
|-----|-------|---------|------|
| [股票技术面因子](特色数据/stk_factor.md) | stk_factor | 5000分 | 技术面因子 |

---

## 本项目使用的API

| 用途 | 接口 | 文档 |
|-----|-----|------|
| ETF日线行情 | `pro.fund_daily()` | [fund_daily](ETF专题/fund_daily.md) |
| ETF份额数据 | `pro.etf_share_size()` | [etf_share_size](ETF专题/etf_share_size.md) |
| 基金净值 | `pro.fund_nav()` | [fund_nav](公募基金/fund_nav.md) |
| 交易日历 | `pro.trade_cal()` | [trade_cal](股票基础/trade_cal.md) |

---

## 代码格式规范

Tushare代码格式：`代码.交易所后缀`

| 交易所 | 后缀 | 示例 |
|-------|-----|------|
| 上海证券交易所 | .SH | 510300.SH |
| 深圳证券交易所 | .SZ | 159915.SZ |
| 北京证券交易所 | .BJ | 8XXXX.BJ |

---

## 积分说明

- 免费接口：注册即可使用
- 120分：基础行情数据
- 500分：指数成分数据
- 5000分：技术因子数据
- 8000分：ETF份额规模数据

积分获取方式：https://tushare.pro/document/1?doc_id=13

---

## 项目分析报告

- [API使用分析报告](APIDOC分析报告.md) - ETF数据获取问题分析与解决方案
