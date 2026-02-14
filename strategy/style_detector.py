"""市场风格判断模块（v2.1）

识别当前市场是大盘主导还是小盘主导，动态调整宽基/行业配置比例。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class StyleBiasResult:
    """风格判断结果"""
    style: str                    # 'large_cap' | 'small_cap' | 'neutral'
    confidence: float            # 0.0-1.0 置信度
    broad_based_ratio: float     # 宽基仓位建议 (0.4-0.7)
    sector_ratio: float          # 行业仓位建议 (0.3-0.6)
    large_cap_focus: Optional[bool]  # 是否聚焦大盘股
    preferred_broad: list        # 推荐的宽基ETF代码
    allocation_adjustment: Dict  # 完整配置调整建议


class StyleDetector:
    """市场风格检测器

    通过大盘/小盘收益差、资金流比、波动率比等指标判断当前市场风格。
    """

    def __init__(
        self,
        large_cap_index: str = "510300",    # 沪深300 ETF
        small_cap_index: str = "512100",    # 中证1000 ETF
        lookback_days: int = 20,
        style_confirm_threshold: int = 3,    # 连续3次确认才切换
        min_hold_days: int = 10,             # 最少持有10天
    ):
        self.large_cap_index = large_cap_index
        self.small_cap_index = small_cap_index
        self.lookback_days = lookback_days

        # 风格切换过滤器状态
        self.current_style = "neutral"
        self.style_counter = 0
        self.style_confirm_threshold = style_confirm_threshold
        self.last_switch_date: Optional[pd.Timestamp] = None
        self.min_hold_days = min_hold_days

    def detect_style(
        self,
        date: pd.Timestamp,
        market_data: Dict[str, pd.DataFrame]
    ) -> StyleBiasResult:
        """检测当前市场风格

        Args:
            date: 当前日期
            market_data: 市场数据字典 {code: DataFrame}

        Returns:
            StyleBiasResult: 风格判断结果
        """
        # 获取大盘/小盘数据
        large_df = market_data.get(self.large_cap_index)
        small_df = market_data.get(self.small_cap_index)

        if large_df is None or small_df is None:
            # 数据缺失，返回中性
            return self._neutral_result()

        # 计算收益差
        return_diff = self._calc_return_diff(large_df, small_df, date)

        # 计算资金流比
        flow_ratio = self._calc_flow_ratio(large_df, small_df, date)

        # 计算波动率比
        vol_ratio = self._calc_volatility_ratio(large_df, small_df, date)

        # 计算风格动量持续性
        style_momentum = self._calc_style_momentum(large_df, small_df, date)

        # 判断风格
        style, confidence = self._classify_style(
            return_diff, flow_ratio, vol_ratio, style_momentum
        )

        # 应用风格切换过滤器
        confirmed_style = self._apply_style_filter(date, style)

        # 生成配置建议
        return self._generate_allocation(confirmed_style, confidence)

    def _calc_return_diff(
        self,
        large_df: pd.DataFrame,
        small_df: pd.DataFrame,
        date: pd.Timestamp
    ) -> float:
        """计算大盘/小盘收益差"""
        large_return = self._get_period_return(large_df, date, self.lookback_days)
        small_return = self._get_period_return(small_df, date, self.lookback_days)
        return large_return - small_return

    def _calc_flow_ratio(
        self,
        large_df: pd.DataFrame,
        small_df: pd.DataFrame,
        date: pd.Timestamp
    ) -> float:
        """计算资金流比"""
        large_flow = self._get_period_flow(large_df, date, self.lookback_days)
        small_flow = self._get_period_flow(small_df, date, self.lookback_days)

        if small_flow == 0:
            return 1.0
        return large_flow / small_flow

    def _calc_volatility_ratio(
        self,
        large_df: pd.DataFrame,
        small_df: pd.DataFrame,
        date: pd.Timestamp
    ) -> float:
        """计算波动率比"""
        large_vol = self._get_volatility(large_df, date, self.lookback_days)
        small_vol = self._get_volatility(small_df, date, self.lookback_days)

        if small_vol == 0:
            return 1.0
        return large_vol / small_vol

    def _calc_style_momentum(
        self,
        large_df: pd.DataFrame,
        small_df: pd.DataFrame,
        date: pd.Timestamp
    ) -> float:
        """计算风格动量持续性（收益差近5日标准差）"""
        diffs = []
        for i in range(5):
            check_date = date - pd.Timedelta(days=i)
            large_ret = self._get_period_return(large_df, check_date, 5)
            small_ret = self._get_period_return(small_df, check_date, 5)
            diffs.append(large_ret - small_ret)

        return np.std(diffs) if diffs else 0.0

    def _classify_style(
        self,
        return_diff: float,
        flow_ratio: float,
        vol_ratio: float,
        style_momentum: float
    ) -> Tuple[str, float]:
        """分类市场风格"""
        # 大盘主导条件
        if return_diff > 0.03 and flow_ratio > 1.2:
            confidence = min(1.0, (return_diff - 0.03) / 0.05 +
                           (flow_ratio - 1.2) / 0.8)
            return "large_cap", confidence

        # 小盘主导条件
        elif return_diff < -0.03 and flow_ratio < 0.8:
            confidence = min(1.0, (-return_diff - 0.03) / 0.05 +
                           (0.8 - flow_ratio) / 0.4)
            return "small_cap", confidence

        # 中性
        else:
            return "neutral", 0.5

    def _apply_style_filter(self, date: pd.Timestamp, detected_style: str) -> str:
        """应用风格切换过滤器"""
        # 检查最小持有期
        if self.last_switch_date is not None:
            days_held = (date - self.last_switch_date).days
            if days_held < self.min_hold_days:
                return self.current_style

        # 检查风格一致性
        if detected_style == self.current_style:
            self.style_counter = 0
            return self.current_style
        else:
            self.style_counter += 1
            if self.style_counter >= self.style_confirm_threshold:
                # 确认切换
                self.current_style = detected_style
                self.style_counter = 0
                self.last_switch_date = date
                return detected_style
            else:
                # 缓冲期，保持原风格
                return self.current_style

    def _generate_allocation(
        self,
        style: str,
        confidence: float
    ) -> StyleBiasResult:
        """生成配置建议"""
        if style == "large_cap":
            return StyleBiasResult(
                style=style,
                confidence=confidence,
                broad_based_ratio=0.6,
                sector_ratio=0.4,
                large_cap_focus=True,
                preferred_broad=["510300", "159601", "510500"],
                allocation_adjustment={
                    "focus": "大盘蓝筹",
                    "avoid": ["159537", "512100"],  # 回避微盘/小盘
                    "factor_weights": {
                        "momentum": 1.5,
                        "fund_flow": 0.8,
                        "valuation": 1.2
                    }
                }
            )
        elif style == "small_cap":
            return StyleBiasResult(
                style=style,
                confidence=confidence,
                broad_based_ratio=0.4,
                sector_ratio=0.6,
                large_cap_focus=False,
                preferred_broad=["512100", "159537", "588000"],
                allocation_adjustment={
                    "focus": "科技成长",
                    "factor_weights": {
                        "momentum": 1.3,
                        "fund_flow": 1.2,
                        "flow_acceleration": 1.3
                    }
                }
            )
        else:
            return self._neutral_result()

    def _neutral_result(self) -> StyleBiasResult:
        """中性风格结果"""
        return StyleBiasResult(
            style="neutral",
            confidence=0.5,
            broad_based_ratio=0.5,
            sector_ratio=0.5,
            large_cap_focus=None,
            preferred_broad=["510300", "510500", "512100"],
            allocation_adjustment={}
        )

    # Helper methods
    def _get_period_return(
        self,
        df: pd.DataFrame,
        date: pd.Timestamp,
        days: int
    ) -> float:
        """计算区间收益率"""
        if df is None or df.empty:
            return 0.0

        df = df[df["date"] <= date].copy()
        if len(df) < days:
            return 0.0

        end_price = df.iloc[-1]["close"]
        start_price = df.iloc[-min(days, len(df))]["close"]

        return (end_price - start_price) / start_price if start_price > 0 else 0.0

    def _get_period_flow(
        self,
        df: pd.DataFrame,
        date: pd.Timestamp,
        days: int
    ) -> float:
        """计算区间资金流"""
        if df is None or df.empty or "share_total" not in df.columns:
            return 0.0

        df = df[df["date"] <= date].copy()
        if len(df) < 2:
            return 0.0

        recent = df.iloc[-min(days, len(df)):]
        if len(recent) < 2:
            return 0.0

        flow = recent["share_total"].diff().sum()
        return flow if not pd.isna(flow) else 0.0

    def _get_volatility(
        self,
        df: pd.DataFrame,
        date: pd.Timestamp,
        days: int
    ) -> float:
        """计算波动率"""
        if df is None or df.empty:
            return 0.0

        df = df[df["date"] <= date].copy()
        if len(df) < days:
            return 0.0

        recent = df.iloc[-min(days, len(df)):]
        if len(recent) < 2:
            return 0.0

        returns = recent["close"].pct_change().dropna()
        return returns.std() if len(returns) > 0 else 0.0
