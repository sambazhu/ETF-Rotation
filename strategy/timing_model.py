"""趋势择时模型模块（v2.2）

评估市场趋势强度，动态调整仓位和调仓频率。
新增：MACD 趋势确认指标
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass
class TrendStrengthResult:
    """趋势强度结果"""
    score: float                      # 0-100 趋势强度得分
    regime: str                       # 'strong_uptrend', 'uptrend', 'sideways', 'downtrend', 'strong_downtrend'
    recommended_position: float       # 0.0-1.0 建议仓位
    components: Dict[str, float]      # 各组件得分


class TimingModel:
    """趋势择时模型（v2.2 新增MACD）"""

    def __init__(self, timing_config: Dict):
        self.config = timing_config
        self.benchmark = timing_config.get("benchmark_index", "510300")
        self.ma_periods = timing_config.get("ma_periods", [5, 10, 20, 60])

    def calculate_trend_strength(
        self,
        date: pd.Timestamp,
        market_data: Dict[str, pd.DataFrame]
    ) -> TrendStrengthResult:
        """计算市场趋势强度（v2.2 加入MACD）"""
        # 获取基准数据
        benchmark_df = market_data.get(self.benchmark)
        if benchmark_df is None or benchmark_df.empty:
            for code in ["510300", "000300"]:
                if code in market_data:
                    benchmark_df = market_data[code]
                    break

        if benchmark_df is None or benchmark_df.empty:
            return TrendStrengthResult(
                score=50,
                regime="sideways",
                recommended_position=0.5,
                components={}
            )

        # 1. 均线系统排列（25%，原30%降低）
        ma_score = self._calc_ma_alignment(benchmark_df, date)

        # 2. 价格动量（20%，原25%降低）
        momentum_score = self._calc_momentum_score(benchmark_df, date)

        # 3. 波动率趋势（20%）
        vol_score = self._calc_volatility_score(benchmark_df, date)

        # 4. 成交量确认（15%）
        volume_score = self._calc_volume_score(benchmark_df, date)

        # 5. MACD趋势确认（v2.2 新增，10%）
        macd_score = self._calc_macd_score(benchmark_df, date)

        # 6. 宏观趋势协同（10%，预留与宏观信号协同）
        macro_sync_score = 10  # 默认中性，可由外部传入宏观评分调整

        # 综合评分（满分100）
        total_score = ma_score + momentum_score + vol_score + volume_score + macd_score + macro_sync_score

        # 确定市场状态和仓位
        thresholds = self.config.get("trend_thresholds", {})
        multipliers = self.config.get("position_multipliers", {})

        if total_score >= thresholds.get("strong_uptrend", 80):
            regime = "strong_uptrend"
            position = multipliers.get("strong_uptrend", 1.0)
        elif total_score >= thresholds.get("uptrend", 60):
            regime = "uptrend"
            position = multipliers.get("uptrend", 0.8)
        elif total_score >= thresholds.get("sideways", 40):
            regime = "sideways"
            position = multipliers.get("sideways", 0.5)
        elif total_score >= thresholds.get("downtrend", 20):
            regime = "downtrend"
            position = multipliers.get("downtrend", 0.3)
        else:
            regime = "strong_downtrend"
            position = multipliers.get("strong_downtrend", 0.0)

        return TrendStrengthResult(
            score=total_score,
            regime=regime,
            recommended_position=position,
            components={
                "ma_score": ma_score,
                "momentum_score": momentum_score,
                "vol_score": vol_score,
                "volume_score": volume_score,
                "macd_score": macd_score,
                "macro_sync_score": macro_sync_score,
            }
        )

    def adjust_position(
        self,
        base_position: float,
        trend_strength: TrendStrengthResult,
        style_bias
    ) -> float:
        """根据趋势强度和风格调整仓位

        Args:
            base_position: 基础仓位（由宏观评分决定）
            trend_strength: 趋势强度结果
            style_bias: 风格判断结果

        Returns:
            float: 调整后的仓位
        """
        # 趋势调整
        trend_adj = trend_strength.recommended_position

        # 风格调整
        style_multipliers = self.config.get("style_multipliers", {})
        style_adj = style_multipliers.get(style_bias.style, 1.0)

        # 综合调整
        adjusted = base_position * trend_adj * style_adj

        return max(0.0, min(1.0, adjusted))

    def get_rebalance_interval(self, trend_regime: str) -> int:
        """根据趋势状态获取调仓间隔"""
        intervals = self.config.get("rebalance_intervals", {})
        return intervals.get(trend_regime, 10)

    # Helper methods
    def _calc_ma_alignment(self, df: pd.DataFrame, date: pd.Timestamp) -> float:
        """计算均线系统排列得分（0-30）"""
        df = df[df["date"] <= date].copy()
        if len(df) < 60:
            return 15

        # 计算各期均线
        for period in self.ma_periods:
            df[f"ma{period}"] = df["close"].rolling(period).mean()

        latest = df.iloc[-1]

        score = 0
        # 多头排列检查
        if latest.get("ma5", 0) > latest.get("ma10", 0):
            score += 10
        if latest.get("ma10", 0) > latest.get("ma20", 0):
            score += 10
        if latest.get("ma20", 0) > latest.get("ma60", 0):
            score += 10

        return score

    def _calc_momentum_score(self, df: pd.DataFrame, date: pd.Timestamp) -> float:
        """计算价格动量得分（0-25）"""
        df = df[df["date"] <= date].copy()
        if len(df) < 20:
            return 12.5

        current_price = df.iloc[-1]["close"]
        ma20 = df.iloc[-20:]["close"].mean()

        if ma20 == 0:
            return 12.5

        deviation = (current_price - ma20) / ma20 * 100
        # 偏离度-5%到+5%映射到0-25
        score = (deviation + 5) / 10 * 25
        return max(0, min(25, score))

    def _calc_volatility_score(self, df: pd.DataFrame, date: pd.Timestamp) -> float:
        """计算波动率趋势得分（0-20）"""
        df = df[df["date"] <= date].copy()
        if len(df) < 60:
            return 10

        returns = df["close"].pct_change().dropna()
        if len(returns) < 60:
            return 10

        vol20 = returns.iloc[-20:].std()
        vol60 = returns.iloc[-60:].std()

        if vol60 == 0:
            return 10

        vol_ratio = vol20 / vol60
        # 波动率比率<0.8表示波动收敛，趋势可能形成
        score = (1 - vol_ratio) / 0.5 * 20
        return max(0, min(20, score))

    def _calc_volume_score(self, df: pd.DataFrame, date: pd.Timestamp) -> float:
        """计算成交量确认得分（0-15）"""
        df = df[df["date"] <= date].copy()
        if len(df) < 20 or "volume" not in df.columns:
            return 7.5

        vol5 = df.iloc[-5:]["volume"].mean()
        vol20 = df.iloc[-20:]["volume"].mean()

        if vol20 == 0:
            return 7.5

        volume_ratio = vol5 / vol20
        # 量比0.8-1.4映射到0-15
        score = (volume_ratio - 0.8) / 0.6 * 15
        return max(0, min(15, score))

    def _calc_macd_score(self, df: pd.DataFrame, date: pd.Timestamp) -> float:
        """计算MACD趋势确认得分（0-10，v2.2新增）

        使用标准MACD参数：SHORT=12, LONG=26, M=9
        评分逻辑：
        - MACD柱状图>0且DIF>DEA：多头排列，得分高
        - MACD柱状图<0且DIF<DEA：空头排列，得分低
        - 金叉/死叉附近：过渡状态，中等得分
        """
        df = df[df["date"] <= date].copy()
        if len(df) < 35:  # 至少需要26+9=35天数据
            return 5  # 中性

        close = df["close"].values

        # 计算EMA12和EMA26
        ema12 = self._calculate_ema(close, 12)
        ema26 = self._calculate_ema(close, 26)

        # 计算DIF和DEA
        dif = ema12 - ema26
        dea = self._calculate_ema(dif, 9)

        # 计算MACD柱状图 (BAR)
        macd_bar = (dif - dea) * 2

        if len(macd_bar) < 2:
            return 5

        # 当前值
        current_dif = dif[-1]
        current_dea = dea[-1]
        current_bar = macd_bar[-1]
        prev_bar = macd_bar[-2]

        # 评分逻辑
        score = 5  # 基准分

        # MACD柱状图正负
        if current_bar > 0:
            score += 2  # 多头区域
            # 柱状图扩大（加速）
            if current_bar > prev_bar:
                score += 2
        else:
            score -= 2  # 空头区域
            # 柱状图扩大（加速下跌）
            if current_bar < prev_bar:
                score -= 2

        # DIF与DEA关系
        if current_dif > current_dea:
            score += 1  # 金叉后或维持金叉
        else:
            score -= 1  # 死叉后或维持死叉

        # DIF位置（零轴上下）
        if current_dif > 0:
            score += 1  # 零轴上方，强势
        else:
            score -= 1  # 零轴下方，弱势

        return max(0, min(10, score))

    @staticmethod
    def _calculate_ema(data: np.ndarray, period: int) -> np.ndarray:
        """计算指数移动平均

        Args:
            data: 价格数据数组
            period: EMA周期

        Returns:
            EMA数组
        """
        multiplier = 2 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]

        for i in range(1, len(data)):
            ema[i] = (data[i] - ema[i-1]) * multiplier + ema[i-1]

        return ema
