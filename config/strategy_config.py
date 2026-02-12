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

    # 分层调仓配置（优化：降低调仓频率）
    "rebalance_freq": {
        "macro": "monthly",           # 宏观仓位：月频
        "broad_based": "monthly",     # 宽基轮动：月频（原双周频）
        "sector": "biweekly",         # 行业轮动：双周频（原信号触发式）
        "stop_loss": "daily",         # 止损止盈：每日
    },

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
        "macro_net_inflow_days": 5,   # 优化：增加回看天数（原3）
        "broad_mfi_days": 5,
        "sector_flow_days": 5,        # 优化：增加回看天数（原3）
        "flow_accel_short": 3,    # 资金流加速度-近期窗口
        "flow_accel_long": 6,     # 资金流加速度-前期窗口（3+3）
        "pdi_days": 20,
        "momentum_short": 5,
        "momentum_long": 20,
        "volatility_days": 20,
        "valuation_days": 252,
        "standardize_window": 60, # 滚动Z-score标准化窗口
    },
    # ─── 评分阈值（优化：提高阈值减少交易） ───
    "thresholds": {
        "broad_main": 50,             # 提高（原40）
        "broad_aux": 25,              # 提高（原20）
        "sector_main": 70,            # 提高（原60）
        "sector_aux": 45,             # 提高（原40）
        "sector_avoid": 25,           # 提高（原20）
    },
    # ─── 评分缩放系数 ───
    "scale_factor": 33.3,  # Z-score最大±3 → 评分映射到±100
    # ─── sigmoid平滑系数 ───
    "sigmoid_smoothing": 15,
    # ─── 过热过滤器（优化：更严格的过滤） ───
    "overheat_threshold": 0.12,       # 降低阈值（原15%）
    "overheat_decay": 0.6,            # 增加衰减（原0.5）
    "overheat_lookback_days": 10,
    # ─── 交易成本控制（优化：提高门槛） ───
    "min_trade_threshold": 0.08,      # 单品种仓位变化<8%不调仓（原5%）
    "min_score_change": 20,           # 评分变化<20不触发买卖（原15）
}


RISK_CONFIG = {
    # ─── 仓位约束 ───
    "max_single_position": 0.25,     # 降低单品种上限（原30%）
    "max_sector_count": 5,
    "min_sector_count": 3,
    "broad_ratio_range": (0.40, 0.60),

    # ─── 多层止损止盈体系（优化：放宽止损阈值） ───
    # 层级1：个股快速止损
    "single_trailing_stop": 0.10,    # 放宽到10%（原8%）
    "single_hard_stop": 0.12,        # 放宽到12%（原10%）

    # 层级2：组合层面
    "portfolio_drawdown_warning": 0.06,   # 放宽到6%（原5%）
    "portfolio_drawdown_reduce": 0.10,    # 放宽到10%（原8%）
    "portfolio_drawdown_exit": 0.15,      # 放宽到15%（原12%）

    # 层级3：利润保护
    "profit_lock_threshold": 0.20,        # 提高到20%（原15%）
    "profit_lock_trailing": 0.10,         # 放宽到10%（原8%）

    # 冷静期
    "cooldown_days": 5,                   # 全部清仓后冷静5个交易日

    # ─── 震荡市识别（优化：更严格的震荡市判断） ───
    "choppy_score_threshold": 15,         # 提高（原10）
    "choppy_vol_percentile": 30,          # 提高（原25）
    "choppy_min_score_change": 40,        # 提高（原30）
    "choppy_max_single_position": 0.15,   # 震荡市降低集中度
}
