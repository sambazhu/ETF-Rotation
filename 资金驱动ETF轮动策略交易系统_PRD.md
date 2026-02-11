# 资金驱动ETF轮动策略交易系统 - 产品需求文档

**文档版本**：v2.0
**创建日期**：2026-02-06
**最后更新**：2026-02-10
**策略类型**：三层量化轮动（宏观→宽基→行业）
**目标用户**：个人投资者、量化爱好者

---

## 一、项目概述

### 1.1 产品定位

基于**ETF资金流向、折溢价行为和动量指标**的三层量化轮动策略系统，旨在通过数据驱动的方式实现：
- **收益目标**：超越沪深300等宽基指数
- **风险控制**：动态调整仓位，控制最大回撤

### 1.2 核心架构

```
┌─────────────────────────────────────────┐
│   第一层：宏观仓位（低频，月）          │
│   判断市场处于牛市/熊市/震荡市           │
│   决定总股票仓位：0%-100%               │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│   第二层：宽基轮动（中频，双周）        │
│   在宽基池内择优，确定风格配置           │
│   大盘/中盘/小盘/成长/价值               │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│   第三层：行业轮动（高频，信号触发）    │
│   聚焦资金流入强势赛道                   │
│   科技/消费/医药/金融/周期等             │
└─────────────────────────────────────────┘
```

### 1.3 适用范围

| 项目 | 说明 |
|------|------|
| **标的范围** | 国内沪深北交易所场内非跨境现货类ETF |
| **排除品种** | 跨境ETF、T+0品种（货币/债券/黄金）、期货期权衍生品 |
| **推荐资金** | 10万-100万，适合中长期投资 |
| **投资周期** | 分层调仓（宏观月频/宽基双周/行业信号触发），持有周期2-8周 |

---

## 二、策略逻辑

### 2.1 驱动因子权重

| 因子 | 权重 | 说明 |
|------|------|------|
| **资金流（份额变动）** | 35%-40% | 机构资金的T-1真实流向 |
| **资金流加速度** | 10%-15% | 资金流的二阶导数，捕捉流入/流出拐点 |
| **盘中溢价代理** | 5%-10% | ETF盘中溢价率日内变化，T+0获取，弥补份额数据滞后 |
| **折溢价行为** | 15%-20% | 一二级市场定价偏差的量化反映 |
| **动量/估值** | 15%-20% | 趋势确认与风险控制 |

> **资金流分级原则**：区分"持续小幅流入"（机构建仓信号，权重高）与"短期大额流入"（事件驱动，权重低），前者对后续收益的预测力更强。

#### 资金流加速度计算

```python
# 资金流加速度 = 资金流变化率（二阶导数）
资金流加速度 = (近3日资金流强度 - 前3日资金流强度) / abs(前3日资金流强度)
# 正值：资金流入加速（买入增强信号）
# 负值：资金流入减速或转为流出（减仓预警信号）
```

#### 盘中溢价代理指标

```python
# 使用收盘时点溢价率日内变化作为T+0资金流代理
盘中溢价变化 = 收盘溢价率 - 开盘溢价率
# 正值：盘中资金持续流入推高溢价（看多信号）
# 负值：盘中资金流出压低溢价（看空信号）
```

### 2.2 因子标准化方法（通用）

> 所有三层指标在计算综合评分前，均需通过以下方法进行标准化，以保证不同量纲因子的可比性。

```python
import numpy as np

def standardize(series, window=60):
    """滚动Z-score标准化
    Args:
        series: 原始因子值序列 (pd.Series)
        window: 滚动窗口天数，默认60个交易日（约3个月）
    Returns:
        标准化后的因子值，范围约(-3, +3)，经winsorize处理
    """
    rolling_mean = series.rolling(window, min_periods=20).mean()
    rolling_std = series.rolling(window, min_periods=20).std()
    z_score = (series - rolling_mean) / rolling_std.clip(lower=1e-8)
    # Winsorize: 将极端值限制在[-3, +3]范围内，避免异常值主导评分
    return z_score.clip(-3, 3)

# 最终综合评分 = ∑(标准化因子值 × 权重) × 缩放系数
# 缩放系数将评分映射到约(-100, +100)的直觉化区间
SCALE_FACTOR = 33.3  # 当所有因子Z-score=3时，加权和=3，×33.3≈100
```

### 2.3 三层指标体系

#### 第一层：宏观环境指标

| 指标 | 计算公式 | 权重 | 阈值/信号 |
|------|----------|------|-----------|
| 全市场ETF净流入 | ∑(3日累计净流入) / 总成交额 | 50% | 连续3日>0且放大 → 积极 |
| 全市场溢价率均值 | 市值加权平均溢价率 | 30% | >+0.3%过热；<-0.3%恐慌 |
| 宽基动量排名均值 | 沪深300/500/1000近20日收益中位数 | 20% | >0.5% → 牛市；<-0.5% → 熊市 |

**宏观综合评分**：
```python
# 1. 分别计算各因子原始值
net_inflow_raw = calc_market_net_inflow(date)   # 全市场3日累计净流入/总成交额
accel_raw = calc_flow_acceleration(date)         # 资金流加速度
premium_raw = calc_market_premium(date)           # 市值加权平均溢价率
intraday_prem_raw = calc_intraday_premium(date)  # 盘中溢价变化
momentum_raw = calc_broad_momentum(date)          # 宽基20日收益中位数

# 2. 标准化（使用2.2节定义的通用方法）
net_inflow_z = standardize(net_inflow_series)[date]
accel_z = standardize(accel_series)[date]
premium_z = standardize(premium_series)[date]
intraday_prem_z = standardize(intraday_prem_series)[date]
momentum_z = standardize(momentum_series)[date]

# 3. 加权合成（含资金流加速度和盘中溢价代理）
score = (net_inflow_z * 0.35 + accel_z * 0.15 + intraday_prem_z * 0.10
         + premium_z * 0.20 + momentum_z * 0.20) * SCALE_FACTOR
```

**总仓位规则（自适应动态阈值 + 仓位连续化）**：
```python
import math

def adaptive_threshold(scores_history, percentile=75):
    """基于近期评分分布动态确定阈值，避免固定阈值在不同市场环境下失效"""
    upper = np.percentile(scores_history[-60:], percentile)
    lower = np.percentile(scores_history[-60:], 100 - percentile)
    return upper, lower

def smooth_position(score, min_pos=0.0, max_pos=1.0):
    """使用sigmoid函数将评分映射到连续仓位，消除阈值引起的仓位跳变"""
    ratio = 1 / (1 + math.exp(-score / 15))  # 15为平滑系数
    return min_pos + (max_pos - min_pos) * ratio

# 总股票仓位 = sigmoid(宏观评分)，范围0%-100%，平滑过渡
总股票仓位 = smooth_position(score, min_pos=0.0, max_pos=1.0)
# 极端负分→接近0%仓位，极端正分→接近100%仓位，中间区域平滑过渡
```

#### 第二层：宽基轮动指标

**宽基池（10只）**：

> **设计原则**：宽基池仅包含覆盖面广的宽基指数和风格指数ETF，不包含单一行业/主题ETF，以避免与行业池产生仓位重叠。

| 代码 | 名称 | 风格 | 覆盖范围 |
|------|------|------|----------|
| 510300 | 沪深300 | 大盘价值 | 大盘蓝筹 |
| 159601 | 中证A50 | 大盘核心 | 各行业龙头50只 |
| 510500 | 中证500 | 中盘 | 中盘成长 |
| 512100 | 中证1000 | 小盘 | 小盘股票 |
| 159537 | 国证2000 | 微盘 | 微盘股覆盖 |
| 588000 | 科创50 | 科技成长 | 科创板科技 |
| 159915 | 创业板 | 成长 | 创业板成长股 |
| 512890 | 红利低波 | 价值防御 | 高股息低波动 |
| 512000 | 券商 | 弹性 | 市场Beta |
| 515000 | 科技 | 科技主题 | 科技板块 |

**指标体系**：

| 指标 | 计算公式 | 权重 |
|------|----------|------|
| 资金流强度 (MFI) | 近5日累计净流入 / 近5日日均成交额 ×100 | 40% |
| 资金流加速度 (MFA) | (近3日MFI - 前3日MFI) / abs(前3日MFI) | 15% |
| 折溢价行为 (PDI) | 当前溢价率在近20日区间分位数（映射-100~+100） | 25% |
| 多周期动量 (CMC) | (5日收益×0.5 + 20日收益×0.5) / 20日波动率 | 20% |

**宽基综合评分**：
```python
# 各因子先通过2.2节的standardize()标准化，再加权合成
MFI_z = standardize(MFI_series)[date]
MFA_z = standardize(MFA_series)[date]   # 资金流加速度
PDI_z = standardize(PDI_series)[date]
CMC_z = standardize(CMC_series)[date]

score = (MFI_z * 0.40 + MFA_z * 0.15 + (-PDI_z) * 0.25 + CMC_z * 0.20) * SCALE_FACTOR
# 注：PDI取负，因为溢价越高越不划算（折价+资金流入=买入信号）
```

**评分阈值**：
- `>40`：该风格为主配（总宽基仓位的50%+）
- `20-40`：该风格为次配（30%左右）
- `<0`：不配置

#### 第三层：行业轮动指标

**行业池（20只）**：

| 代码 | 名称 | 类别 | 主要成分 |
|------|------|------|----------|
| 512480 | 半导体 | 科技 | 芯片设计/制造/封测 |
| 159819 | 人工智能 | 科技 | AI算法/算力/应用 |
| 512760 | 芯片 | 科技 | 半导体设备/材料 |
| 562500 | 机器人 | 科技 | 工业机器人/自动化 |
| 515700 | 光伏 | 新能源 | 光伏产业链 |
| 516160 | 储能 | 新能源 | 电池/储能系统 |
| 512690 | 白酒 | 消费 | 白酒龙头 |
| 159928 | 消费 | 消费 | 食品饮料/家电 |
| 512010 | 医药 | 医药 | 医药研发/制造 |
| 512170 | 医疗 | 医药 | 医疗器械/服务 |
| 512880 | 证券 | 金融 | 券商板块 |
| 512070 | 银行 | 金融 | 银行板块 |
| 512400 | 有色金属 | 周期 | 铜/铝/锂等 |
| 512200 | 房地产 | 周期 | 房地产开发 |
| 560660 | 工业母机 | 高端制造 | 数控机床/精密制造 |
| 159790 | 电池 | 新能源 | 动力电池/储能电池 |
| 515220 | 煤炭 | 周期 | 煤炭开采 |
| 516950 | 基建 | 周期 | 建筑/建材 |
| 512660 | 军工 | 主题 | 国防军工 |
| 512680 | 家电 | 消费 | 家电龙头 |

**指标体系**：

| 指标 | 计算公式 | 权重 |
|------|----------|------|
| 行业资金净流入 | 近3日累计净流入 / 近3日日均成交额 ×100 | 40% |
| 资金流加速度 | (近3日资金流强度 - 前3日) / abs(前3日) | 15% |
| 盘中溢价变化 | 收盘溢价率 - 开盘溢价率 | 10% |
| 相对动量 | 相对于中证800的20日超额收益 | 25% |
| 估值分位 | 当前PE在近1年区间的分位数（越低越好） | 10% |

**行业综合评分**：
```python
# 各因子先通过2.2节的standardize()标准化，再加权合成
fund_flow_z = standardize(fund_flow_series)[date]
fund_accel_z = standardize(fund_accel_series)[date]    # 资金流加速度
intraday_prem_z = standardize(intraday_prem_series)[date]  # 盘中溢价变化
rel_momentum_z = standardize(rel_momentum_series)[date]
valuation_z = standardize(valuation_series)[date]       # 注：估值分位越低越好

score = (fund_flow_z * 0.40 + fund_accel_z * 0.15 + intraday_prem_z * 0.10
         + rel_momentum_z * 0.25 + (-valuation_z) * 0.10) * SCALE_FACTOR
# 估值分位取负：低估值→高分

# 过热过滤器：避免追高
if calc_return(code, days=10) > 0.15:  # 近10日涨幅超15%
    score *= 0.5  # 衰减处理，降低追高风险
```

**评分阈值**：
- `>60`：该行业为进攻主力（单行业≤30%）
- `40-60`：该行业为辅助配置（单行业≤15%）
- `<20`：回避

---

## 三、交易规则

### 3.1 信号生成与调仓频率（分层式）

| 层级 | 指标更新 | 决策频率 | 执行频率 | 设计理由 |
|------|----------|----------|----------|----------|
| 宏观仓位 | 每日 | 每月 | 月初第一个交易日 | 宏观环境变化慢，月频足够 |
| 宽基轮动 | 每日 | 双周 | 每双周周一 | 风格切换周期较长 |
| 行业轮动 | 每日 | 信号触发式 | 当评分变化>阈值时 | 及时捕捉行业轮动机会 |
| 止损/止盈 | 每日 | 每日 | 每日 | 风控不能等 |

### 3.2 仓位约束

```python
# 总股票仓位：0%-100%（通过sigmoid平滑函数动态计算）
总股票仓位 = smooth_position(宏观综合评分)

# 仓位分配
宽基部分 = 总股票仓位 × (40%-60%)  # 风格底仓
行业部分 = 总股票仓位 × (40%-60%)  # 进攻仓位

# 单品种限制
行业单品种 ≤ 30%
宽基单品种 ≤ 30%
现金/债券 ≥ 0%  # 极端风险时提升
```

### 3.3 调仓规则

#### 调仓信号

| 条件 | 动作 |
|------|------|
| 当前持仓标的评分进入前3名且>40分 | 保留/加仓 |
| 当前持仓标的评分跌出前5名或<20分 | 减仓/卖出 |
| 新出现评分>60的标的 | 优先买入 |
| 连续2周评分下降幅度>30分 | 减半仓 |
| 行业内部分散：至少配置3个不同行业 | 避免过度集中 |

#### 交易成本控制（最小调仓门槛）

```python
# 仅当仓位变化超过门槛时才执行交易，避免频繁小额调仓侵蚀收益
MIN_TRADE_THRESHOLD = 0.05  # 单品种仓位变化<5%不调仓
MIN_SCORE_CHANGE = 15       # 评分变化<15不触发买卖

# 过热过滤器：避免追高买入
if 某ETF近10日涨幅 > 15%:
    该ETF评分 *= 0.5  # 衰减处理，降低追高风险
```

### 3.4 多层止损止盈体系

```python
STOP_LOSS_CONFIG = {
    # ─── 层级1：个股快速止损（每日检查） ───
    'single_etf_trailing_stop': 0.08,   # 从持仓期间最高点回撤8%即止损
    'single_etf_hard_stop': 0.10,       # 从买入价下跌10%无条件清仓
    
    # ─── 层级2：组合层面（每日检查） ───
    'portfolio_drawdown_warning': 0.05,  # 组合回撤5%发出预警，冻结新买入
    'portfolio_drawdown_reduce': 0.08,   # 组合回撤8%将总仓位降至30%
    'portfolio_drawdown_exit': 0.12,     # 组合回撤12%全部清仓，冷静期5个交易日
    
    # ─── 层级3：利润保护（追踪止盈） ───
    'profit_lock_threshold': 0.15,       # 盈利超15%后启动追踪止盈
    'profit_lock_trailing': 0.08,        # 从盈利高点回撤8%锁定利润
}
```

### 3.5 震荡市识别与应对

```python
# 震荡市识别条件
if abs(宏观评分) < 10 and 近20日波动率 < 历史25分位数:
    # 进入震荡市模式：降低调仓频率，提高调仓门槛
    调仓频率 = '月频'             # 降低到月频
    MIN_SCORE_CHANGE = 30           # 提高触发门槛
    行业单品种上限 = 15%          # 降低集中度
    # 目标：少动多看，避免资金被震荡磨损
```

---

## 四、数据需求

### 4.1 数据清单

| 数据类型 | 字段 | 频率 | 用途 | 来源 |
|----------|------|------|------|------|
| ETF行情数据 | date, code, name, open, high, low, close, volume, amount | 日线 | 价格、成交量计算 | AKShare/Tushare |
| ETF份额数据 | date, code, share_total | 每日（T-1） | 资金流计算 | 基金公司官网 |
| IOPV净值 | date, code, iopv | 每日 | 折溢价计算 | 交易所行情 |
| 指数成分股 | date, index_code, stock_list | 每日 | 基准对比 | Tushare |
| 交易日历 | date, is_trading_day | 静态 | 调仓日判断 | 同上 |

### 4.2 核心计算公式

#### 资金净流入估算

```python
# ETF资金净流入（万元）
当日资金净流入 = (当日份额 - 昨日份额) × 当日收盘价

# 资金流强度（标准化）
资金流强度 = 近N日累计净流入 / 近N日日均成交额 × 100
```

#### 折溢价率

```python
# 单日折溢价率
折溢价率 = (收盘价 - IOPV) / IOPV × 100%

# 折溢价行为指数（在近期区间的位置）
PDI = (当前折溢价率 - 近20日最小值) / (近20日最大值 - 近20日最小值) × 200 - 100
# 结果范围：-100（极端折价）到 +100（极端溢价）
```

#### 多周期动量

```python
# 夏普比率思想的动量合成
动量得分 = (5日收益率 × 0.5 + 20日收益率 × 0.5) / 20日波动率

# 波动率 = 收益率标准差 × sqrt(252)
```

---

## 五、回测框架

### 5.1 回测参数

```python
BACKTEST_CONFIG = {
    'start_date': '2022-01-01',      # 回测开始日期
    'end_date': '2025-12-31',        # 回测结束日期
    'initial_capital': 500000,       # 初始资金50万（10-100万范围内）
    'commission_rate': 0.0003,       # 佣金万分之三
    'slippage_rate': 0.001,          # 滑点千分之一
    'benchmark': '000300.SH',        # 沪深300基准
    'min_etf_amount': 1000000,       # ETF最小成交额门槛（100万）
    
    # 分层调仓配置
    'rebalance_freq': {
        'macro': 'monthly',          # 宏观仓位：月频
        'broad_based': 'biweekly',   # 宽基轮动：双周频
        'sector': 'signal_triggered',# 行业轮动：信号触发式
        'stop_loss': 'daily',        # 止损止盈：每日
    },
    
    # 交易成本控制
    'min_trade_threshold': 0.05,     # 单品种仓位变化<5%不调仓
    'min_score_change': 15,          # 评分变化<15不触发买卖
}
```

### 5.2 回测模块设计

| 模块 | 功能 |
|------|------|
| `DataFetcher` | 数据获取（行情、份额、净值） |
| `DataProcessor` | 数据清洗、缺失值处理、标准化 |
| `SignalGenerator` | 每日生成三层信号（宏观/宽基/行业） |
| `PortfolioManager` | 仓位管理、调仓逻辑 |
| `TradeExecutor` | 模拟交易执行（考虑冲击成本） |
| `BacktestEngine` | 回测主引擎，控制时间推进 |
| `PerformanceAnalyzer` | 绩效评估（收益、回撤、夏普等） |

### 5.3 回测输出

| 输出类型 | 内容 |
|----------|------|
| **绩效指标** | 年化收益、最大回撤、夏普比率、胜率、盈亏比 |
| **净值曲线** | 策略净值、基准净值（沪深300）对比 |
| **仓位历史** | 每日总仓位、宽基/行业配置变化 |
| **交易记录** | 每笔买入/卖出明细（标的、价格、数量、时间） |
| **信号历史** | 每日三层信号评分（宏观/宽基/行业） |

---

## 六、系统架构

### 6.1 目录结构

```
ETF_Rotation_Strategy/
├── README.md                        # 项目说明
├── requirements.txt                 # 依赖库
├── config/                          # 配置文件
│   ├── etf_pool.py                 # ETF标的池定义
│   └── strategy_config.py          # 策略参数配置
├── data/                            # 数据获取与处理
│   ├── data_fetcher.py             # 数据获取模块
│   ├── data_processor.py           # 数据处理模块
│   └── data_sources.py             # 数据源定义
├── strategy/                        # 策略核心
│   ├── macro_signal.py             # 宏观环境判断（第一层）
│   ├── broad_based_rotation.py     # 宽基轮动（第二层）
│   ├── sector_rotation.py          # 行业轮动（第三层）
│   └── signal_generator.py         # 综合信号生成
├── backtest/                        # 回测系统
│   ├── backtest_engine.py          # 回测引擎
│   ├── performance.py              # 绩效评估
│   └── trade_logger.py             # 交易记录
└── main.py                          # 程序入口
```

### 6.2 核心类设计

#### DataFetcher

```python
class DataFetcher:
    """数据获取器"""

    def __init__(self, data_source='akshare'):
        self.source = data_source

    def fetch_etf_daily(self, code, start_date, end_date):
        """获取ETF日线行情
        Args:
            code: ETF代码（如'510300'）
            start_date: 开始日期（'YYYY-MM-DD'）
            end_date: 结束日期（'YYYY-MM-DD'）
        Returns:
            DataFrame: date, open, high, low, close, volume, amount
        """
        pass

    def fetch_etf_share(self, code, date):
        """获取ETF份额数据
        Args:
            code: ETF代码
            date: 日期
        Returns:
            float: 份额（万份）
        """
        pass

    def fetch_iopv(self, code, date):
        """获取ETF实时净值
        Args:
            code: ETF代码
            date: 日期
        Returns:
            float: IOPV净值
        """
        pass
```

#### SignalGenerator

```python
class SignalGenerator:
    """信号生成器"""

    def calculate_macro_score(self, date):
        """计算宏观综合评分
        Args:
            date: 日期
        Returns:
            dict: {
                'score': 综合评分,
                'net_inflow_score': 资金流得分,
                'premium_score': 溢价率得分,
                'momentum_score': 动量得分,
                'total_equity_ratio': 建议总股票仓位
            }
        """
        pass

    def calculate_broad_based_score(self, code, date):
        """计算宽基综合评分
        Args:
            code: ETF代码
            date: 日期
        Returns:
            dict: {
                'code': 代码,
                'name': 名称,
                'score': 综合评分,
                'mfi': 资金流强度,
                'pdi': 折溢价行为,
                'cmc': 多周期动量,
                'rank': 排名
            }
        """
        pass

    def calculate_sector_score(self, code, date):
        """计算行业综合评分（同上）"""
        pass

    def generate_signals(self, date):
        """生成当日三层信号
        Args:
            date: 日期
        Returns:
            dict: {
                'macro': 宏观信号,
                'broad_based': 宽基信号列表（按评分排序）,
                'sector': 行业信号列表（按评分排序）
            }
        """
        pass
```

#### PortfolioManager

```python
class PortfolioManager:
    """组合管理器"""

    def __init__(self, initial_capital=1000000):
        self.cash = initial_capital
        self.positions = {}  # {code: {'quantity': 数量, 'avg_cost': 平均成本}}
        self.total_value = initial_capital

    def rebalance(self, signals, total_equity_ratio):
        """根据信号调仓
        Args:
            signals: 三层信号
            total_equity_ratio: 总股票仓位比例
        Returns:
            list: 交易指令列表
        """
        pass

    def calculate_position_size(self, score, total_equity, max_single_ratio=0.3):
        """根据评分计算仓位
        Args:
            score: 评分
            total_equity: 总权益
            max_single_ratio: 单品种最大仓位
        Returns:
            float: 建议仓位金额
        """
        pass

    def get_current_holdings(self):
        """获取当前持仓"""
        pass
```

#### BacktestEngine

```python
class BacktestEngine:
    """回测引擎"""

    def __init__(self, config):
        self.config = config
        self.data_fetcher = DataFetcher(config['data_source'])
        self.signal_generator = SignalGenerator()
        self.portfolio = PortfolioManager(config['initial_capital'])
        self.trade_log = []
        self.daily_pnl = []

    def run(self):
        """运行回测"""
        trading_days = self.get_trading_days()

        for date in trading_days:
            # 1. 获取当日数据
            self.update_data(date)

            # 2. 生成信号
            signals = self.signal_generator.generate_signals(date)

            # 3. 每日检查止损止盈（不限于调仓日）
            stop_trades = self.portfolio.check_stop_loss(date)
            if stop_trades:
                self.record_trades(stop_trades)

            # 4. 分层调仓
            if self.is_macro_rebalance_day(date):    # 月频
                self.portfolio.rebalance_macro(signals)
            if self.is_broad_rebalance_day(date):    # 双周频
                self.portfolio.rebalance_broad(signals)
            if self.is_sector_signal_triggered(signals):  # 信号触发
                self.portfolio.rebalance_sector(signals)

            # 5. 记录每日净值
            self.record_daily_pnl(date)

        # 6. 生成报告
        self.generate_report()

    def generate_report(self):
        """生成回测报告"""
        pass
```

---

## 七、实施计划

| 阶段 | 任务 | 预计工作量 |
|------|------|-----------|
| **Phase 1** | 数据获取模块开发 | 2-3天 |
| **Phase 2** | 指标计算模块开发 | 2-3天 |
| **Phase 3** | 信号生成与仓位管理 | 2-3天 |
| **Phase 4** | 回测引擎与绩效评估 | 2-3天 |
| **Phase 5** | 回测优化与参数调优 | 3-5天 |
| **Phase 6** | 实盘对接（可选） | 2-3天 |

**总计**：约2-3周（个人开发）

---

## 八、风险与注意事项

| 风险类型 | 说明 | 应对措施 |
|----------|------|----------|
| **数据质量** | 份额数据延迟、缺失 | 多数据源备份、缺失值处理 |
| **过拟合风险** | 参数在历史数据上过度优化 | 样本外测试、滚动窗口验证 |
| **交易成本** | 高频调仓导致成本侵蚀 | 控制调仓频率、设置最小变动阈值 |
| **流动性风险** | 部分行业ETF流动性差 | 限制单品种仓位、设置成交额门槛 |
| **极端行情** | 黑天鹅事件导致大幅回撤 | 设置硬止损、极端情况空仓 |

---

## 九、后续优化方向

1. **参数优化**：使用遗传算法、网格搜索优化指标权重
2. **机器学习增强**：引入LSTM/XGBoost预测资金流趋势
3. **多因子融合**：加入估值、盈利、情绪等因子
4. **动态频率**：根据市场波动率动态调整调仓频率
5. **实盘监控**：开发实时信号推送、仓位监控系统

---

## 十、附录

### 10.1 国内场内非跨境现货类ETF概况

| 类别 | 数量（约） | 特点 |
|------|-----------|------|
| 宽基指数 | 160只 | 覆盖大盘、中盘、小盘、成长、价值等 |
| 行业/主题 | 600-800只 | 消费、医药、科技、新能源、半导体等 |
| 策略指数 | 150只 | 红利、低波、质量、动量等 |
| 债券类 | 350+只 | 国债、信用债、可转债（排除） |
| 商品/货币 | 数十只 | 黄金、货币基金（排除） |
| **合计（不含跨境）** | **~1300-1500只** | 股票型占主体 |

### 10.2 交易规则摘要

| 项目 | 规则 |
|------|------|
| 交易时间 | 9:30-11:30，13:00-15:00 |
| 最小单位 | 100份（1手） |
| 交易制度 | 股票型ETF为T+1 |
| 交易费用 | 佣金（无印花税） |
| 价格精度 | 0.001元 |

### 10.3 参考资料

- [东方财富：场内基金品种分类](http://quote.eastmoney.com/)
- [Wind：ETF资金流数据与溢价率统计](https://www.wind.com.cn/)
- [同花顺iFinD：ETF申赎清单与份额变化](http://www.10jqka.com.cn/)
- [天天基金：场内基金规模与分类](http://fund.eastmoney.com/)
