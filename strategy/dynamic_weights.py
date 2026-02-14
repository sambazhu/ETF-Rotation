"""动态因子权重调整模块（v2.1）

根据市场环境（趋势/震荡/过渡）和市场风格（大盘/小盘主导）
动态调整各层因子权重。
"""

from __future__ import annotations

from typing import Dict


class DynamicWeightAdjuster:
    """动态权重调整器"""

    def __init__(self, dynamic_config: Dict):
        self.config = dynamic_config

    def adjust_weights(
        self,
        market_regime: str,
        market_style: str,
        base_weights: Dict[str, Dict[str, float]]
    ) -> Dict[str, Dict[str, float]]:
        """根据市场环境和风格调整权重

        Args:
            market_regime: 'trending', 'choppy', 'transitional'
            market_style: 'large_cap', 'small_cap', 'neutral'
            base_weights: {'macro': {...}, 'broad': {...}, 'sector': {...}}

        Returns:
            调整后的权重字典
        """
        result = {}

        # 1. 应用市场环境权重
        for layer in ['macro', 'broad', 'sector']:
            regime_weights = self.config.get(f'{layer}_weights', {}).get(market_regime, {})
            if regime_weights:
                result[layer] = regime_weights.copy()
            else:
                result[layer] = base_weights.get(layer, {}).copy()

        # 2. 应用风格调整
        result = self._apply_style_adjustment(result, market_style)

        return result

    def _apply_style_adjustment(
        self,
        weights: Dict[str, Dict[str, float]],
        market_style: str
    ) -> Dict[str, Dict[str, float]]:
        """根据市场风格微调权重"""
        adjusted = {k: v.copy() for k, v in weights.items()}

        if market_style == 'large_cap':
            # 大盘主导：动量权重提升，资金流权重降低
            for layer in adjusted:
                if 'momentum' in adjusted[layer]:
                    adjusted[layer]['momentum'] *= 1.2
                if 'fund_flow' in adjusted[layer] or 'mfi' in adjusted[layer]:
                    key = 'fund_flow' if 'fund_flow' in adjusted[layer] else 'mfi'
                    adjusted[layer][key] *= 0.9

        elif market_style == 'small_cap':
            # 小盘主导：资金流和加速度权重提升
            for layer in adjusted:
                if 'fund_flow' in adjusted[layer] or 'mfi' in adjusted[layer]:
                    key = 'fund_flow' if 'fund_flow' in adjusted[layer] else 'mfi'
                    adjusted[layer][key] *= 1.15
                if 'flow_acceleration' in adjusted[layer] or 'mfa' in adjusted[layer]:
                    key = 'flow_acceleration' if 'flow_acceleration' in adjusted[layer] else 'mfa'
                    adjusted[layer][key] *= 1.15

        # 归一化每层权重
        for layer in adjusted:
            total = sum(adjusted[layer].values())
            if total > 0:
                adjusted[layer] = {k: v/total for k, v in adjusted[layer].items()}

        return adjusted
