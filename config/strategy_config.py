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
    # ─── 宏观层权重（5因子）─优化：大幅降低资金流权重，提高动量权重 ───
    "macro_weights": {
        "net_inflow": 0.15,        # 大幅降低（原0.35→0.25→0.15）
        "flow_acceleration": 0.10, # 降低（原0.15）
        "intraday_premium": 0.10,
        "premium": 0.10,           # 降低（原0.15）
        "momentum": 0.55,          # 大幅提高（原0.20→0.35→0.55），主导趋势跟踪
    },
    # ─── 宽基层权重（4因子）─优化：大幅降低MFI权重，提高动量权重 ───
    "broad_weights": {
        "mfi": 0.20,               # 大幅降低（原0.40→0.35→0.20）
        "mfa": 0.10,               # 降低（原0.15）
        "pdi": 0.20,               # 维持
        "cmc": 0.50,               # 大幅提高（原0.20→0.30→0.50）
    },
    # ─── 行业层权重（5因子）─优化：降低资金流权重，提高动量权重 ───
    "sector_weights": {
        "fund_flow": 0.20,         # 大幅降低（原0.40→0.35→0.20）
        "flow_acceleration": 0.10, # 降低（原0.15）
        "intraday_premium": 0.10,
        "relative_momentum": 0.45, # 大幅提高（原0.25→0.30→0.45）
        "valuation": 0.15,         # 略提高（原0.10）
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
    # ─── 评分阈值（优化：平衡阈值，提高信号敏感度） ───
    "thresholds": {
        "broad_main": 40,             # 恢复（原50过高）
        "broad_aux": 20,              # 恢复（原25过高）
        "sector_main": 55,            # 降低（原70过高）
        "sector_aux": 35,             # 降低（原45过高）
        "sector_avoid": 20,           # 恢复（原25过高）
    },
    # ─── 评分缩放系数 ───
    "scale_factor": 33.3,  # Z-score最大±3 → 评分映射到±100
    # ─── sigmoid平滑系数（优化：大幅降低使中等正评分对应更高仓位） ───
    "sigmoid_smoothing": 5,  # 原15→8→6→5，score=+10 → ~88% 仓位
    # ─── 过热过滤器（优化：更严格的过滤） ───
    "overheat_threshold": 0.12,       # 降低阈值（原15%）
    "overheat_decay": 0.6,            # 增加衰减（原0.5）
    "overheat_lookback_days": 10,
    # ─── 交易成本控制（优化：降低门槛增加交易活跃度） ───
    "min_trade_threshold": 0.08,      # 单品种仓位变化<8%不调仓（原15%）
    "min_score_change": 20,           # 评分变化<20不触发买卖（原35）
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


# ─── v2.1 新增：风格判断配置 ───
STYLE_CONFIG = {
    "large_cap_index": "510300",      # 沪深300
    "small_cap_index": "512100",      # 中证1000
    "lookback_days": 20,
    "return_diff_threshold": 0.03,    # 3%收益差阈值
    "flow_ratio_threshold": 1.2,      # 资金流比阈值
    "style_confirm_threshold": 3,     # 连续3次确认才切换
    "min_hold_days": 10,              # 最少持有10天

    # 风格调整映射
    "allocation_adjustment": {
        "large_cap": {
            "broad_based_ratio": 0.6,   # 大盘主导时增加宽基配置
            "sector_ratio": 0.4,
            "factor_multipliers": {
                "momentum": 1.5,
                "fund_flow": 0.8,
                "valuation": 1.2
            }
        },
        "small_cap": {
            "broad_based_ratio": 0.4,   # 小盘主导时减少宽基
            "sector_ratio": 0.6,
            "factor_multipliers": {
                "momentum": 1.3,
                "fund_flow": 1.2,
                "flow_acceleration": 1.3
            }
        },
        "neutral": {
            "broad_based_ratio": 0.5,
            "sector_ratio": 0.5,
            "factor_multipliers": {}
        }
    }
}


# ─── v2.1 新增：动态因子权重配置 ───
DYNAMIC_WEIGHT_CONFIG = {
    # 市场环境分类阈值
    "market_regime_thresholds": {
        "trending": {"vol_percentile": 60, "macro_score_abs": 40},
        "choppy": {"vol_percentile": 40, "macro_score_abs": 20},
    },

    # 宏观层动态权重
    "macro_weights": {
        "trending": {
            "net_inflow": 0.30,
            "flow_acceleration": 0.10,
            "intraday_premium": 0.10,
            "premium": 0.15,
            "momentum": 0.35,
        },
        "choppy": {
            "net_inflow": 0.40,
            "flow_acceleration": 0.15,
            "intraday_premium": 0.15,
            "premium": 0.25,
            "momentum": 0.05,
        },
        "transitional": {
            "net_inflow": 0.35,
            "flow_acceleration": 0.15,
            "intraday_premium": 0.10,
            "premium": 0.20,
            "momentum": 0.20,
        }
    },

    # 宽基层动态权重
    "broad_weights": {
        "trending": {
            "mfi": 0.30,
            "mfa": 0.10,
            "pdi": 0.20,
            "cmc": 0.40,
        },
        "choppy": {
            "mfi": 0.45,
            "mfa": 0.20,
            "pdi": 0.25,
            "cmc": 0.10,
        },
        "transitional": {
            "mfi": 0.40,
            "mfa": 0.15,
            "pdi": 0.25,
            "cmc": 0.20,
        }
    },

    # 行业层动态权重
    "sector_weights": {
        "trending": {
            "fund_flow": 0.30,
            "flow_acceleration": 0.10,
            "intraday_premium": 0.10,
            "relative_momentum": 0.40,
            "valuation": 0.10,
        },
        "choppy": {
            "fund_flow": 0.45,
            "flow_acceleration": 0.20,
            "intraday_premium": 0.15,
            "relative_momentum": 0.10,
            "valuation": 0.10,
        },
        "transitional": {
            "fund_flow": 0.40,
            "flow_acceleration": 0.15,
            "intraday_premium": 0.10,
            "relative_momentum": 0.25,
            "valuation": 0.10,
        }
    }
}


# ─── v2.1 新增：择时模型配置 ───
TIMING_CONFIG = {
    "benchmark_index": "510300",      # 沪深300作为基准
    "lookback_days": 20,

    # 趋势强度阈值
    "trend_thresholds": {
        "strong_uptrend": 80,
        "uptrend": 60,
        "sideways": 40,
        "downtrend": 20,
        "strong_downtrend": 0,
    },

    # 仓位调整系数
    "position_multipliers": {
        "strong_uptrend": 1.2,
        "uptrend": 1.0,
        "sideways": 0.7,
        "downtrend": 0.4,
        "strong_downtrend": 0.0,
    },

    # 均线参数
    "ma_periods": [5, 10, 20, 60],

    # 调仓频率（根据趋势状态）
    "rebalance_intervals": {
        "strong_uptrend": 5,     # 强趋势：5天
        "uptrend": 10,           # 上升趋势：10天
        "sideways": 20,          # 震荡：20天
        "downtrend": 30,         # 下行：30天
        "strong_downtrend": 999  # 空仓：不操作
    },

    # 风格调整系数
    "style_multipliers": {
        "large_cap": 1.1,    # 大盘主导，风险较低
        "small_cap": 0.9,    # 小盘主导，波动大
        "neutral": 1.0,
    }
}
