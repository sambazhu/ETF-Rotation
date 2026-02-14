# 资金驱动ETF轮动策略交易系统 - 产品需求文档

**文档版本**：v2.2
**创建日期**：2026-02-06
**最后更新**：2026-02-14
**策略类型**：三层量化轮动（宏观→宽基→行业）+ 风格自适应 + 动态择时 + MACD趋势确认
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

### 2.1 驱动因子权重（动态调整机制 v2.2）

#### 2.1.1 基础权重配置

| 因子 | 默认权重 | 权重范围 | 说明 |
|------|----------|----------|------|
| **资金流（份额变动）** | 35%-40% | 30%-50% | 机构资金的T-1真实流向 |
| **资金流加速度** | 10%-15% | 5%-20% | 资金流的二阶导数，捕捉流入/流出拐点 |
| **盘中溢价代理** | 5%-10% | 0%-15% | ETF盘中溢价率日内变化，T+0获取 |
| **折溢价行为** | 15%-20% | 10%-25% | 一二级市场定价偏差的量化反映 |
| **动量/估值** | 15%-20% | 10%-35% | 趋势确认与风险控制，趋势市可提高 |

#### 2.1.2 市场环境自适应权重调整（v2.2实现）

动态权重调整器根据市场风格动态调整因子权重：

```python
class DynamicWeightAdjuster:
    """动态权重调整器（v2.2实现）"""

    def adjust_weights(self, market_regime, market_style, base_weights):
        """根据市场环境和风格调整权重

        Args:
            market_regime: 'trending', 'choppy', 'transitional'
            market_style: 'large_cap', 'small_cap', 'neutral'
            base_weights: {'macro': {...}, 'broad': {...}, 'sector': {...}}
        """
        # 1. 应用市场环境权重
        for layer in ['macro', 'broad', 'sector']:
            regime_weights = self.config.get(f'{layer}_weights', {}).get(market_regime, {})
            result[layer] = regime_weights.copy() if regime_weights else base_weights[layer].copy()

        # 2. 应用风格调整
        result = self._apply_style_adjustment(result, market_style)
        return result

    def _apply_style_adjustment(self, weights, market_style):
        """根据市场风格微调权重并归一化"""
        if market_style == 'large_cap':
            # 大盘主导：动量权重提升20%，资金流权重降低10%
            for layer in adjusted:
                if 'momentum' in adjusted[layer]:
                    adjusted[layer]['momentum'] *= 1.2
                if 'fund_flow' in adjusted[layer] or 'mfi' in adjusted[layer]:
                    key = 'fund_flow' if 'fund_flow' in adjusted[layer] else 'mfi'
                    adjusted[layer][key] *= 0.9

        elif market_style == 'small_cap':
            # 小盘主导：资金流和加速度权重提升15%
            for layer in adjusted:
                if 'fund_flow' in adjusted[layer] or 'mfi' in adjusted[layer]:
                    key = 'fund_flow' if 'fund_flow' in adjusted[layer] else 'mfi'
                    adjusted[layer][key] *= 1.15
                if 'flow_acceleration' in adjusted[layer] or 'mfa' in adjusted[layer]:
                    key = 'flow_acceleration' if 'flow_acceleration' in adjusted[layer] else 'mfa'
                    adjusted[layer][key] *= 1.15

        # 归一化每层权重（确保总和为1）
        for layer in adjusted:
            total = sum(adjusted[layer].values())
            if total > 0:
                adjusted[layer] = {k: v/total for k, v in adjusted[layer].items()}

        return adjusted
```

#### 2.1.3 动态权重配置示例

```python
# 宏观层动态权重
DYNAMIC_MACRO_WEIGHTS = {
    'trending': {          # 趋势市
        'net_inflow': 0.30,
        'flow_acceleration': 0.10,
        'intraday_premium': 0.10,
        'premium': 0.15,
        'momentum': 0.35,      # 动量权重提高
    },
    'choppy': {            # 震荡市
        'net_inflow': 0.40,
        'flow_acceleration': 0.15,
        'intraday_premium': 0.15,
        'premium': 0.25,       # 折溢价权重提高
        'momentum': 0.05,      # 动量权重降低
    },
    'transitional': {      # 过渡市
        'net_inflow': 0.35,
        'flow_acceleration': 0.15,
        'intraday_premium': 0.10,
        'premium': 0.20,
        'momentum': 0.20,
    }
}
```

#### 2.1.3 资金流分级原则

区分"持续小幅流入"（机构建仓信号，权重高）与"短期大额流入"（事件驱动，权重低），前者对后续收益的预测力更强。

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

---

#### 第二层（扩展）：市场风格判断（新增 v2.1）

**目标**：识别当前市场是大盘主导还是小盘主导，动态调整宽基/行业配置比例

**风格判断指标**：

| 指标 | 计算方法 | 阈值 | 说明 |
|------|----------|------|------|
| 大盘/小盘收益差 | 沪深300 - 中证1000 近20日收益差 | >3%：大盘主导；<-3%：小盘主导 | 核心风格识别指标 |
| 大盘/小盘资金流比 | 沪深300资金流 / 中证1000资金流 | >1.5：大盘主导；<0.67：小盘主导 | 资金流向确认 |
| 大小盘波动率比 | 沪深300波动率 / 中证1000波动率 | <0.8：大盘稳定；>1.2：小盘活跃 | 风险偏好判断 |
| 风格动量持续性 | 收益差近5日标准差 | <2%：风格稳定；>4%：风格轮动快 | 避免频繁切换 |

**风格判断逻辑**：

```python
def detect_market_style(date, lookback=20):
    """判断当前市场风格（大盘/小盘主导）

    Returns:
        dict: {
            'style': 'large_cap' | 'small_cap' | 'neutral',
            'confidence': 0.0-1.0,  # 判断置信度
            'allocation_adjustment': {...}  # 配置调整建议
        }
    """
    # 1. 计算收益差
    large_return = get_index_return('000300', date, lookback)
    small_return = get_index_return('000852', date, lookback)
    return_diff = large_return - small_return

    # 2. 计算资金流比
    large_flow = get_etf_flow('510300', date, lookback)
    small_flow = get_etf_flow('512100', date, lookback)
    flow_ratio = large_flow / small_flow if small_flow != 0 else 1.0

    # 3. 风格判断
    if return_diff > 0.03 and flow_ratio > 1.2:
        style = 'large_cap'
        confidence = min(1.0, (return_diff - 0.03) / 0.05 + (flow_ratio - 1.2) / 0.8)
    elif return_diff < -0.03 and flow_ratio < 0.8:
        style = 'small_cap'
        confidence = min(1.0, (-return_diff - 0.03) / 0.05 + (0.8 - flow_ratio) / 0.4)
    else:
        style = 'neutral'
        confidence = 0.5

    return {'style': style, 'confidence': confidence}
```

**风格切换缓冲机制**：

```python
class StyleRegimeFilter:
    """风格切换过滤器"""

    def __init__(self):
        self.current_style = 'neutral'
        self.style_counter = 0
        self.style_confirm_threshold = 3  # 连续3次确认才切换
        self.min_hold_days = 10

    def update(self, date, detected_style):
        if self.last_switch_date and (date - self.last_switch_date).days < self.min_hold_days:
            return self.current_style

        if detected_style == self.current_style:
            self.style_counter = 0
            return self.current_style
        else:
            self.style_counter += 1
            if self.style_counter >= self.style_confirm_threshold:
                self.current_style = detected_style
                self.style_counter = 0
                self.last_switch_date = date
            return self.current_style
```

---

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

### 2.4 风格判断模块（新增 v2.1）

**目标**：识别当前市场处于大盘主导还是小盘主导，动态调整宽基池权重。

#### 2.4.1 风格判断指标

| 指标 | 计算方式 | 权重 |
|------|----------|------|
| 大盘-小盘收益差 | 沪深300近20日收益 - 中证1000近20日收益 | 40% |
| 大盘-小盘资金流差 | 沪深300ETF近5日净流入 - 中证1000ETF近5日净流入 | 35% |
| 大盘-小盘动量差 | 沪深300 20日动量 - 中证1000 20日动量 | 25% |

#### 2.4.2 风格评分计算

```python
def calculate_style_score(date):
    """计算市场风格偏向分数
    Returns:
        score: 正数=大盘主导，负数=小盘主导，0=均衡
        strength: 风格强度 (0-1)
    """
    # 1. 收益差标准化
    large_cap_return = calc_return('510300', days=20)
    small_cap_return = calc_return('512100', days=20)
    return_diff = large_cap_return - small_cap_return
    return_diff_z = standardize(return_diff_series)[date]

    # 2. 资金流差标准化
    large_flow = calc_net_inflow('510300', days=5)
    small_flow = calc_net_inflow('512100', days=5)
    flow_diff = large_flow - small_flow
    flow_diff_z = standardize(flow_diff_series)[date]

    # 3. 动量差标准化
    large_momentum = calc_momentum('510300', days=20)
    small_momentum = calc_momentum('512100', days=20)
    momentum_diff = large_momentum - small_momentum
    momentum_diff_z = standardize(momentum_diff_series)[date]

    # 加权合成
    style_score = (return_diff_z * 0.40 +
                   flow_diff_z * 0.35 +
                   momentum_diff_z * 0.25) * 33.3

    # 风格强度 (sigmoid映射到0-1)
    style_strength = 1 / (1 + math.exp(-abs(style_score) / 20))

    return style_score, style_strength
```

#### 2.4.3 风格影响权重调整

```python
# 根据风格判断调整宽基评分权重
STYLE_BIAS_CONFIG = {
    'large_cap_dominant': {
        'large_cap_etf_boost': 1.3,      # 大盘ETF评分加权
        'small_cap_etf_discount': 0.7,   # 小盘ETF评分折扣
        'min_large_cap_ratio': 0.6,      # 最低大盘配置60%
    },
    'small_cap_dominant': {
        'small_cap_etf_boost': 1.3,      # 小盘ETF评分加权
        'large_cap_etf_discount': 0.7,   # 大盘ETF评分折扣
        'min_small_cap_ratio': 0.6,      # 最低小盘配置60%
    },
    'balanced': {
        'boost': 1.0,                    # 无加权
        'discount': 1.0,
        'neutral_ratio': 0.5,            # 均衡配置
    }
}

# 风格阈值
if style_score > 30:      # 大盘主导
    market_style = 'large_cap_dominant'
elif style_score < -30:  # 小盘主导
    market_style = 'small_cap_dominant'
else:                     # 均衡市场
    market_style = 'balanced'
```

---

### 2.5 动态因子权重系统（新增 v2.1）

**目标**：根据市场环境动态调整各因子权重，避免固定权重在特定市场失效。

#### 2.5.1 市场环境分类

| 市场环境 | 定义条件 | 特征 |
|----------|----------|------|
| 趋势市 | 20日波动率 > 历史60分位 且 宏观评分绝对值 > 40 | 趋势明确，动量有效 |
| 震荡市 | 20日波动率 < 历史40分位 且 宏观评分绝对值 < 20 | 区间波动，均值回复 |
| 过渡市 | 其他情况 | 不明确，保守配置 |

#### 2.5.2 动态权重配置

```python
# 宏观层动态权重
DYNAMIC_MACRO_WEIGHTS = {
    'trending': {          # 趋势市：动量+资金流权重提高
        'net_inflow': 0.30,
        'flow_acceleration': 0.10,
        'intraday_premium': 0.10,
        'premium': 0.15,
        'momentum': 0.35,      # 动量权重提高
    },
    'choppy': {            # 震荡市：估值+折溢价权重提高
        'net_inflow': 0.40,
        'flow_acceleration': 0.15,
        'intraday_premium': 0.15,
        'premium': 0.25,       # 折溢价权重提高
        'momentum': 0.05,      # 动量权重降低
    },
    'transitional': {      # 过渡市：均衡配置
        'net_inflow': 0.35,
        'flow_acceleration': 0.15,
        'intraday_premium': 0.10,
        'premium': 0.20,
        'momentum': 0.20,
    }
}

# 宽基层动态权重
DYNAMIC_BROAD_WEIGHTS = {
    'trending': {
        'mfi': 0.30,           # 资金流权重降低
        'mfa': 0.10,
        'pdi': 0.20,
        'cmc': 0.40,           # 动量权重提高
    },
    'choppy': {
        'mfi': 0.45,           # 资金流权重提高
        'mfa': 0.20,
        'pdi': 0.25,           # 折溢价权重提高
        'cmc': 0.10,           # 动量权重降低
    },
    'transitional': {
        'mfi': 0.40,
        'mfa': 0.15,
        'pdi': 0.25,
        'cmc': 0.20,
    }
}

# 行业层动态权重
DYNAMIC_SECTOR_WEIGHTS = {
    'trending': {
        'fund_flow': 0.30,
        'flow_acceleration': 0.10,
        'intraday_premium': 0.10,
        'relative_momentum': 0.40,  # 动量权重提高
        'valuation': 0.10,
    },
    'choppy': {
        'fund_flow': 0.45,
        'flow_acceleration': 0.20,
        'intraday_premium': 0.15,
        'relative_momentum': 0.10,  # 动量权重降低
        'valuation': 0.10,
    },
    'transitional': {
        'fund_flow': 0.40,
        'flow_acceleration': 0.15,
        'intraday_premium': 0.10,
        'relative_momentum': 0.25,
        'valuation': 0.10,
    }
}
```

---

### 2.6 动态择时机制（新增 v2.1）

**目标**：根据趋势强度动态调整总仓位，趋势明确时重仓，震荡市时轻仓。

#### 2.6.1 趋势强度评估

```python
def calculate_trend_strength(date):
    """计算市场趋势强度
    Returns:
        strength: 0-1之间的趋势强度值
        direction: 'up', 'down', 'neutral'
    """
    # 多维度趋势确认
    factors = {
        'macro_trend': 1 if abs(macro_score) > 40 else 0,
        'price_trend': 1 if abs(calc_return('510300', days=20)) > 0.05 else 0,
        'flow_trend': 1 if calc_net_inflow('all', days=5) > 0 else 0,
        'volatility_low': 1 if calc_volatility('510300', days=20) < 0.20 else 0,
        'breadth': 1 if calc_market_breadth() > 0.6 else 0,  # 上涨家数占比
    }

    # 趋势强度 = 确认因子占比
    trend_strength = sum(factors.values()) / len(factors)

    # 趋势方向
    if macro_score > 30 and factors['price_trend']:
        direction = 'up'
    elif macro_score < -30 and factors['price_trend']:
        direction = 'down'
    else:
        direction = 'neutral'

    return trend_strength, direction
```

#### 2.6.2 动态仓位调整

```python
# 基础仓位配置
BASE_POSITION_CONFIG = {
    'max_equity_ratio': 1.0,     # 最高权益仓位100%
    'min_equity_ratio': 0.0,     # 最低权益仓位0%
    'neutral_ratio': 0.5,        # 中性仓位50%
}

# 根据趋势强度调整仓位
def adjust_position_by_trend(macro_score, trend_strength, direction):
    """动态调整总权益仓位"""

    # 基础仓位由宏观评分决定（sigmoid平滑）
    base_ratio = 1 / (1 + math.exp(-macro_score / 15))

    # 根据趋势强度调整
    if direction == 'up' and trend_strength > 0.6:
        # 强上升趋势：提高仓位上限
        adjusted_ratio = min(base_ratio * 1.2, 1.0)
    elif direction == 'down' and trend_strength > 0.6:
        # 强下降趋势：降低仓位下限
        adjusted_ratio = base_ratio * 0.5
    elif trend_strength < 0.3:
        # 弱趋势/震荡市：降低仓位至中性附近
        adjusted_ratio = 0.3 + (base_ratio - 0.5) * 0.4  # 压缩波动
    else:
        adjusted_ratio = base_ratio

    return adjusted_ratio

# 分层仓位动态调整
def get_layer_allocation(trend_strength, market_style):
    """根据趋势强度和市场风格调整分层仓位配比"""

    if trend_strength > 0.7:  # 强趋势
        if market_style == 'large_cap_dominant':
            return {'broad_based': 0.7, 'sector': 0.3}  # 重仓宽基
        else:
            return {'broad_based': 0.4, 'sector': 0.6}  # 重仓行业
    elif trend_strength < 0.3:  # 弱趋势/震荡
        return {'broad_based': 0.6, 'sector': 0.2}      # 降低行业暴露
    else:  # 中等趋势
        return {'broad_based': 0.5, 'sector': 0.4}      # 均衡配置
```

#### 2.6.3 择时与风格结合

```python
def generate_final_allocation(date):
    """生成最终仓位配置（结合择时+风格）"""

    # 1. 市场环境判断
    macro_score = calc_macro_score(date)
    trend_strength, direction = calculate_trend_strength(date)
    style_score, style_strength = calculate_style_score(date)

    # 2. 确定市场风格
    if style_score > 30:
        market_style = 'large_cap_dominant'
    elif style_score < -30:
        market_style = 'small_cap_dominant'
    else:
        market_style = 'balanced'

    # 3. 确定市场环境类型
    volatility = calc_volatility('510300', days=20)
    if volatility > np.percentile(historical_vol, 60) and abs(macro_score) > 40:
        market_regime = 'trending'
    elif volatility < np.percentile(historical_vol, 40) and abs(macro_score) < 20:
        market_regime = 'choppy'
    else:
        market_regime = 'transitional'

    # 4. 计算总权益仓位
    total_equity = adjust_position_by_trend(macro_score, trend_strength, direction)

    # 5. 计算分层仓位
    layer_ratio = get_layer_allocation(trend_strength, market_style)

    # 6. 获取动态因子权重
    macro_weights = DYNAMIC_MACRO_WEIGHTS[market_regime]
    broad_weights = DYNAMIC_BROAD_WEIGHTS[market_regime]
    sector_weights = DYNAMIC_SECTOR_WEIGHTS[market_regime]

    # 7. 应用风格调整
    style_config = STYLE_BIAS_CONFIG[market_style]

    return {
        'total_equity_ratio': total_equity,
        'broad_based_ratio': total_equity * layer_ratio['broad_based'],
        'sector_ratio': total_equity * layer_ratio['sector'],
        'market_style': market_style,
        'market_regime': market_regime,
        'trend_strength': trend_strength,
        'style_score': style_score,
        'macro_weights': macro_weights,
        'broad_weights': broad_weights,
        'sector_weights': sector_weights,
        'style_config': style_config,
    }
```

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

### 3.6 趋势择时与动态仓位管理（新增 v2.1）

**目标**：根据市场趋势强度动态调整总仓位，趋势明确时满仓，震荡/下行时降低仓位

#### 3.6.1 趋势强度判断指标

| 指标 | 计算方法 | 权重 | 说明 |
|------|----------|------|------|
| 均线系统排列 | 5/10/20/60日均线多头排列得分 | 30% | 多头排列越完整，趋势越强 |
| 价格动量 | 当前价 vs 20日均线的偏离度 | 25% | 正向偏离越大，趋势越强 |
| 波动率趋势 | 20日波动率 / 60日波动率 | 20% | 比率<0.8表示波动收敛，趋势可能形成 |
| 成交量确认 | 近5日成交量 / 近20日均量 | 15% | 放量上涨确认趋势 |
| 宏观评分趋势 | 宏观评分5日变化率 | 10% | 宏观环境改善确认 |

#### 3.6.2 趋势强度评分计算

```python
def calculate_trend_strength(date):
    """计算市场趋势强度得分（0-100）

    Returns:
        dict: {
            'score': 0-100,           # 趋势强度得分
            'regime': 'strong_uptrend' | 'uptrend' | 'sideways' | 'downtrend' | 'strong_downtrend',
            'recommended_position': 0.0-1.0  # 建议仓位比例
        }
    """
    # 1. 均线系统排列（30%）
    ma5, ma10, ma20, ma60 = get_moving_averages('000300', date)
    ma_score = 0
    if ma5 > ma10: ma_score += 10
    if ma10 > ma20: ma_score += 10
    if ma20 > ma60: ma_score += 10

    # 2. 价格动量（25%）
    price = get_close('000300', date)
    momentum = (price - ma20) / ma20 * 100
    momentum_score = max(0, min(25, (momentum + 5) / 10 * 25))

    # 3. 波动率趋势（20%）
    vol20 = get_volatility('000300', date, 20)
    vol60 = get_volatility('000300', date, 60)
    vol_ratio = vol20 / vol60 if vol60 > 0 else 1.0
    vol_score = max(0, min(20, (1 - vol_ratio) / 0.5 * 20))

    # 4. 成交量确认（15%）
    vol5 = get_avg_volume('000300', date, 5)
    vol20 = get_avg_volume('000300', date, 20)
    volume_ratio = vol5 / vol20 if vol20 > 0 else 1.0
    volume_score = max(0, min(15, (volume_ratio - 0.8) / 0.6 * 15))

    # 5. 宏观评分趋势（10%）
    macro_now = get_macro_score(date)
    macro_5d = get_macro_score(date - 5)
    macro_change = (macro_now - macro_5d) / abs(macro_5d) if macro_5d != 0 else 0
    macro_score = max(0, min(10, (macro_change + 0.2) / 0.4 * 10))

    total_score = ma_score + momentum_score + vol_score + volume_score + macro_score

    # 判断市场状态
    if total_score >= 80:
        regime = 'strong_uptrend'
        position = 1.0
    elif total_score >= 60:
        regime = 'uptrend'
        position = 0.8
    elif total_score >= 40:
        regime = 'sideways'
        position = 0.5
    elif total_score >= 20:
        regime = 'downtrend'
        position = 0.3
    else:
        regime = 'strong_downtrend'
        position = 0.0

    return {
        'score': total_score,
        'regime': regime,
        'recommended_position': position,
        'components': {
            'ma_score': ma_score,
            'momentum_score': momentum_score,
            'vol_score': vol_score,
            'volume_score': volume_score,
            'macro_score': macro_score
        }
    }
```

#### 3.6.3 动态仓位管理规则

```python
def calculate_dynamic_position(macro_score, trend_strength, style_bias):
    """综合计算动态仓位

    Args:
        macro_score: 宏观评分 (-100 to +100)
        trend_strength: 趋势强度 (0 to 100)
        style_bias: 风格判断结果

    Returns:
        float: 0.0-1.0 的目标仓位比例
    """
    # 1. 基础仓位 = 宏观评分映射
    base_position = sigmoid(macro_score / 20)  # 归一化到0-1

    # 2. 趋势调整系数
    trend_multiplier = {
        'strong_uptrend': 1.2,    # 满仓
        'uptrend': 1.0,           # 维持基础仓位
        'sideways': 0.7,          # 降低到70%
        'downtrend': 0.4,         # 降低到40%
        'strong_downtrend': 0.0   # 空仓
    }[trend_strength['regime']]

    # 3. 风格调整（大盘主导时更稳健，可提高仓位）
    style_multiplier = 1.0
    if style_bias['style'] == 'large_cap':
        style_multiplier = 1.1    # 大盘主导，风险较低，可略微提高
    elif style_bias['style'] == 'small_cap':
        style_multiplier = 0.9    # 小盘主导，波动大，略微降低

    # 4. 计算最终仓位
    target_position = base_position * trend_multiplier * style_multiplier

    # 5. 限制在合理范围
    return max(0.0, min(1.0, target_position))
```

#### 3.6.4 择时信号与调仓频率协同

```python
class TimingAdaptiveRebalancer:
    """择时自适应调仓器"""

    def __init__(self):
        self.last_rebalance = None
        self.rebalance_freq = {
            'strong_uptrend': 5,     # 强趋势：5天（提高敏感度）
            'uptrend': 10,           # 上升趋势：10天（双周）
            'sideways': 20,          # 震荡：20天（月频）
            'downtrend': 30,         # 下行：30天（减少操作）
            'strong_downtrend': 999  # 空仓：不操作
        }

    def should_rebalance(self, date, trend_regime, force_signal=False):
        """判断是否应调仓"""
        if force_signal:
            return True

        min_interval = self.rebalance_freq[trend_regime]

        if self.last_rebalance is None:
            return True

        days_since = (date - self.last_rebalance).days
        return days_since >= min_interval
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
│   ├── style_detector.py           # 【新增】市场风格判断
│   ├── timing_model.py             # 【新增】趋势择时模型
│   ├── dynamic_weights.py          # 【新增】动态因子权重
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

### Phase 1: 基础框架（已完成）

| 任务 | 状态 | 说明 |
|------|------|------|
| 数据获取模块 | ✅ | Tushare Pro 数据源接入 |
| 三层信号系统 | ✅ | 宏观/宽基/行业轮动 |
| 回测引擎 | ✅ | 完整回测框架 |
| 风险控制 | ✅ | 多层止损止盈体系 |

### Phase 2: v2.1/v2.2 优化迭代（已完成）

| 任务 | 状态 | 说明 |
|------|------|------|
| **风格判断模块** | ✅ | 大盘/小盘风格检测，带切换缓冲 |
| - 大盘/小盘收益差计算 | ✅ | 20日收益差判断风格 |
| - 资金流比分析 | ✅ | 沪深300/中证1000资金流比 |
| - 风格切换缓冲机制 | ✅ | 连续3次确认+最少持有10天 |
| **动态因子权重** | ✅ | 根据市场风格动态调整权重 |
| - 市场环境识别 | ✅ | trending/choppy/transitional |
| - 权重调整算法 | ✅ | 大盘:动量↑ 小盘:资金流↑ |
| - 与评分系统集成 | ✅ | SignalGenerator集成完成 |
| **趋势择时模型** | ✅ | 多维度趋势评估 |
| - 均线系统排列 | ✅ | 5/10/20/60日均线得分 |
| - 趋势强度评分 | ✅ | 0-100分综合评分 |
| - MACD趋势确认 | ✅ | v2.2新增，权重10% |
| - 动态仓位管理 | ✅ | 根据趋势调整仓位 |
| **数据优化** | ✅ | 净值数据获取+3次重试机制 |
| **回测验证** | ✅ | 2022-2025全周期回测完成 |

### Phase 3: 高级优化（可选）

| 任务 | 预计工作量 | 说明 |
|------|-----------|------|
| 机器学习增强 | 3-5天 | LSTM/XGBoost预测资金流 |
| 参数自动优化 | 2-3天 | 遗传算法/贝叶斯优化 |
| 实盘对接 | 2-3天 | 信号推送、自动交易 |

**总计**：v2.1优化约1周，完整系统约3周

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
