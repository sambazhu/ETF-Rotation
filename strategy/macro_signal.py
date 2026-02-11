"""第一层：宏观仓位信号（v2.0）。

PRD 2.3 第一层要求:
- 5因子: 全市场净流入(0.35), 资金流加速度(0.15), 盘中溢价代理(0.10),
         全市场溢价率(0.20), 宽基动量(0.20)
- 所有因子经滚动Z-score标准化后加权合成
- 总仓位通过sigmoid函数平滑映射（消除阈值跳变）
- 自适应动态阈值（基于近60日评分分位数）
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config.strategy_config import SIGNAL_CONFIG


def _clip_score(value: float, lower: float = -100.0, upper: float = 100.0) -> float:
    return float(np.clip(value, lower, upper))


def smooth_position(score: float, min_pos: float = 0.0, max_pos: float = 1.0,
                    smoothing: float = 15.0) -> float:
    """sigmoid平滑仓位函数，将评分映射到连续仓位 [min_pos, max_pos]。

    score=0 → 仓位50%, score=+45 → ~95%, score=-45 → ~5%
    """
    ratio = 1.0 / (1.0 + math.exp(-score / max(smoothing, 1.0)))
    return min_pos + (max_pos - min_pos) * ratio


def adaptive_threshold(scores_history: List[float], percentile: float = 75.0) -> tuple:
    """基于近60日评分分布动态确定阈值。

    Returns:
        (upper_threshold, lower_threshold)
    """
    if len(scores_history) < 10:
        return (30.0, -30.0)
    recent = scores_history[-60:]
    upper = float(np.percentile(recent, percentile))
    lower = float(np.percentile(recent, 100 - percentile))
    return (upper, lower)


class MacroSignal:
    """根据全市场特征计算宏观评分与总仓位（v2.0 5因子+sigmoid）。"""

    def __init__(self, weights: Optional[Dict[str, float]] = None,
                 scale_factor: Optional[float] = None,
                 sigmoid_smoothing: Optional[float] = None):
        cfg = SIGNAL_CONFIG
        self.weights = weights or cfg["macro_weights"]
        self.scale_factor = scale_factor or cfg.get("scale_factor", 33.3)
        self.sigmoid_smoothing = sigmoid_smoothing or cfg.get("sigmoid_smoothing", 15.0)
        self.scores_history: List[float] = []

    def calculate(self, market_snapshot: pd.DataFrame) -> Dict[str, float]:
        """输入某日全市场聚合快照（宽基ETF行），输出宏观评分与仓位。

        market_snapshot 需要的列:
        - mfi_z (或 net_inflow_z): 资金流强度Z-score
        - mfa_z: 资金流加速度Z-score
        - intraday_premium_proxy_z: 盘中溢价代理Z-score
        - premium_rate_z: 溢价率Z-score
        - cmc_z: 动量Z-score
        """
        if market_snapshot.empty:
            return {
                "score": 0.0,
                "net_inflow_component": 0.0,
                "accel_component": 0.0,
                "intraday_prem_component": 0.0,
                "premium_component": 0.0,
                "momentum_component": 0.0,
                "total_equity_ratio": 0.30,
                "regime": "neutral",
            }

        # 提取各因子Z-score均值（聚合全市场宽基）
        net_inflow_z = self._safe_mean(market_snapshot, "mfi_z")
        accel_z = self._safe_mean(market_snapshot, "mfa_z")
        intraday_prem_z = self._safe_mean(market_snapshot, "intraday_premium_proxy_z")
        premium_z = self._safe_mean(market_snapshot, "premium_rate_z")
        momentum_z = self._safe_mean(market_snapshot, "cmc_z")

        # 加权合成（PRD公式）
        score = (
            net_inflow_z * self.weights.get("net_inflow", 0.35)
            + accel_z * self.weights.get("flow_acceleration", 0.15)
            + intraday_prem_z * self.weights.get("intraday_premium", 0.10)
            + (-premium_z) * self.weights.get("premium", 0.20)  # 高溢价→看空
            + momentum_z * self.weights.get("momentum", 0.20)
        ) * self.scale_factor

        score = _clip_score(score)
        self.scores_history.append(score)

        # sigmoid平滑仓位
        equity_ratio = smooth_position(score, min_pos=0.0, max_pos=1.0,
                                       smoothing=self.sigmoid_smoothing)

        # 判断市场状态
        regime = self._classify_regime(score)

        return {
            "score": float(score),
            "net_inflow_component": float(net_inflow_z * self.scale_factor),
            "accel_component": float(accel_z * self.scale_factor),
            "intraday_prem_component": float(intraday_prem_z * self.scale_factor),
            "premium_component": float(premium_z * self.scale_factor),
            "momentum_component": float(momentum_z * self.scale_factor),
            "total_equity_ratio": round(float(equity_ratio), 4),
            "regime": regime,
        }

    def _classify_regime(self, score: float) -> str:
        """根据评分和历史分位判断市场状态。"""
        upper, lower = adaptive_threshold(self.scores_history)
        if score > upper:
            return "bullish"
        elif score < lower:
            return "bearish"
        else:
            return "neutral"

    @staticmethod
    def _safe_mean(df: pd.DataFrame, col: str) -> float:
        """安全地取某列的均值，列不存在或全NA返回0。"""
        if col not in df.columns:
            return 0.0
        val = df[col].mean()
        return 0.0 if pd.isna(val) else float(val)
