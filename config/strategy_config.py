"""策略配置文件（v2.0）。

包含回测参数、信号权重、风控参数，与PRD v2.0保持一致。
"""

from __future__ import annotations


BACKTEST_CONFIG = {
    "start_date": "2022-01-01",
    "end_date": "2025-12-31",
    "initial_capital": 500_000,       # 初始资金50万（10-100万范围内）
    "commission_rate": 0.0003,        # 佣金万分之三
    "slippage_rate": 0.001,           # 滑点千分之一
    "benchmark": "510300",            # 沪深300ETF
    "min_etf_amount": 1_000_000,      # ETF最小成交额门槛（100万）
    "data_source": "akshare",
    "fallback_to_mock": True,

    # 分层调仓配置
    "rebalance_freq": {
        "macro": "monthly",           # 宏观仓位：月频
        "broad_based": "biweekly",    # 宽基轮动：双周频
        "sector": "signal_triggered", # 行业轮动：信号触发式
        "stop_loss": "daily",         # 止损止盈：每日
    },

    # 交易成本控制
    "min_trade_threshold": 0.05,      # 单品种仓位变化<5%不调仓
    "min_score_change": 15,           # 评分变化<15不触发买卖
}


SIGNAL_CONFIG = {
    # ─── 宏观层权重（5因子） ───
    "macro_weights": {
        "net_inflow": 0.35,
        "flow_acceleration": 0.15,
        "intraday_premium": 0.10,
        "premium": 0.20,
        "momentum": 0.20,
    },
    # ─── 宽基层权重（4因子） ───
    "broad_weights": {
        "mfi": 0.40,
        "mfa": 0.15,            # 资金流加速度
        "pdi": 0.25,
        "cmc": 0.20,
    },
    # ─── 行业层权重（5因子） ───
    "sector_weights": {
        "fund_flow": 0.40,
        "flow_acceleration": 0.15,
        "intraday_premium": 0.10,
        "relative_momentum": 0.25,
        "valuation": 0.10,
    },
    # ─── 回看窗口期 ───
    "lookback": {
        "macro_net_inflow_days": 3,
        "broad_mfi_days": 5,
        "sector_flow_days": 3,
        "flow_accel_short": 3,    # 资金流加速度-近期窗口
        "flow_accel_long": 6,     # 资金流加速度-前期窗口（3+3）
        "pdi_days": 20,
        "momentum_short": 5,
        "momentum_long": 20,
        "volatility_days": 20,
        "valuation_days": 252,
        "standardize_window": 60, # 滚动Z-score标准化窗口
    },
    # ─── 评分阈值 ───
    "thresholds": {
        "broad_main": 40,
        "broad_aux": 20,
        "sector_main": 60,
        "sector_aux": 40,
        "sector_avoid": 20,
    },
    # ─── 评分缩放系数 ───
    "scale_factor": 33.3,  # Z-score最大±3 → 评分映射到±100
    # ─── sigmoid平滑系数 ───
    "sigmoid_smoothing": 15,
    # ─── 过热过滤器 ───
    "overheat_threshold": 0.15,     # 近10日涨幅>15%
    "overheat_decay": 0.5,          # 评分衰减系数
    "overheat_lookback_days": 10,
}


RISK_CONFIG = {
    # ─── 仓位约束 ───
    "max_single_position": 0.30,     # 单品种≤30%
    "max_sector_count": 5,
    "min_sector_count": 3,
    "broad_ratio_range": (0.40, 0.60),

    # ─── 多层止损止盈体系 ───
    # 层级1：个股快速止损
    "single_trailing_stop": 0.08,    # 从持仓最高点回撤8%
    "single_hard_stop": 0.10,        # 从买入价下跌10%

    # 层级2：组合层面
    "portfolio_drawdown_warning": 0.05,   # 组合回撤5%冻结新买入
    "portfolio_drawdown_reduce": 0.08,    # 组合回撤8%降仓至30%
    "portfolio_drawdown_exit": 0.12,      # 组合回撤12%全部清仓

    # 层级3：利润保护
    "profit_lock_threshold": 0.15,        # 盈利超15%启动追踪止盈
    "profit_lock_trailing": 0.08,         # 从盈利高点回撤8%锁定

    # 冷静期
    "cooldown_days": 5,                   # 全部清仓后冷静5个交易日

    # ─── 震荡市识别 ───
    "choppy_score_threshold": 10,         # |宏观评分| < 10
    "choppy_vol_percentile": 25,          # 波动率 < 历史25分位
    "choppy_min_score_change": 30,        # 震荡市提高触发门槛
    "choppy_max_single_position": 0.15,   # 震荡市降低集中度
}
