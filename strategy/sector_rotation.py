"""第三层：行业轮动评分（v2.0）。

PRD 2.3 第三层要求:
- 5因子: 行业资金流(0.40), 资金流加速度(0.15), 盘中溢价变化(0.10),
         相对动量(0.25), 估值分位(0.10, 取负)
- 所有因子经滚动Z-score标准化后加权合成
- 过热过滤器: 近10日涨幅>15%则评分×0.5
- 评分阈值: >60进攻主力, 40-60辅助, <20回避
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config.strategy_config import SIGNAL_CONFIG


class SectorRotation:
    """计算行业ETF评分并排序（v2.0 5因子+过热过滤器）。"""

    def __init__(self, weights: Optional[Dict[str, float]] = None,
                 scale_factor: Optional[float] = None,
                 overheat_threshold: Optional[float] = None,
                 overheat_decay: Optional[float] = None):
        cfg = SIGNAL_CONFIG
        self.weights = weights or cfg["sector_weights"]
        self.scale_factor = scale_factor or cfg.get("scale_factor", 33.3)
        self.overheat_threshold = overheat_threshold or cfg.get("overheat_threshold", 0.15)
        self.overheat_decay = overheat_decay or cfg.get("overheat_decay", 0.5)

    def rank(self, sector_snapshot: pd.DataFrame,
             benchmark_ret_20d: float = 0.0) -> pd.DataFrame:
        """对行业ETF计算综合评分并排序。

        sector_snapshot 每行一只行业ETF，需要的列:
        - code, name, category
        - sector_flow_strength_z: 行业资金流Z-score
        - mfa_z: 资金流加速度Z-score
        - intraday_premium_proxy_z: 盘中溢价变化Z-score
        - ret_20d: 20日收益率（用于相对动量）
        - valuation_pct_z: 估值分位Z-score
        - ret_10d: 10日收益率（用于过热过滤）
        """
        if sector_snapshot.empty:
            return pd.DataFrame(
                columns=["code", "name", "category", "score",
                         "sector_flow_z", "accel_z", "premium_z",
                         "rel_momentum", "valuation_z",
                         "overheat", "rank", "signal"]
            )

        scored = sector_snapshot.copy()

        # 提取Z-score
        flow_z = self._safe_col(scored, "sector_flow_strength_z")
        accel_z = self._safe_col(scored, "mfa_z")
        prem_z = self._safe_col(scored, "intraday_premium_proxy_z")
        val_z = self._safe_col(scored, "valuation_pct_z")

        # 相对动量: 自身20日收益 - 基准20日收益，再标准化为Z-score
        if "ret_20d" in scored.columns:
            scored["rel_momentum"] = scored["ret_20d"].fillna(0) - benchmark_ret_20d
            # 简单标准化: 相对动量 / 近期标准差
            rm_std = scored["rel_momentum"].std()
            if rm_std > 1e-8:
                scored["rel_momentum_z"] = (scored["rel_momentum"] / rm_std).clip(-3, 3)
            else:
                scored["rel_momentum_z"] = 0.0
        else:
            scored["rel_momentum"] = 0.0
            scored["rel_momentum_z"] = 0.0

        rel_mom_z = scored["rel_momentum_z"]

        # 加权合成
        scored["score"] = (
            flow_z * self.weights.get("fund_flow", 0.40)
            + accel_z * self.weights.get("flow_acceleration", 0.15)
            + prem_z * self.weights.get("intraday_premium", 0.10)
            + rel_mom_z * self.weights.get("relative_momentum", 0.25)
            + (-val_z) * self.weights.get("valuation", 0.10)  # 低估值→高分
        ) * self.scale_factor

        # 过热过滤器
        scored["overheat"] = False
        if "ret_10d" in scored.columns:
            overheat_mask = scored["ret_10d"].fillna(0) > self.overheat_threshold
            scored.loc[overheat_mask, "score"] *= self.overheat_decay
            scored.loc[overheat_mask, "overheat"] = True

        scored["score"] = scored["score"].clip(-100, 100)

        # 排序
        scored = scored.sort_values("score", ascending=False).reset_index(drop=True)
        scored["rank"] = np.arange(1, len(scored) + 1)

        # 信号标签
        scored["signal"] = scored["score"].apply(self._score_to_signal)

        # 输出列
        out_cols = ["code", "score", "rank", "signal", "overheat", "rel_momentum"]
        for col in ["name", "category", "sector_flow_strength_z", "mfa_z",
                     "intraday_premium_proxy_z", "valuation_pct_z"]:
            if col in scored.columns:
                out_cols.append(col)

        return scored[[c for c in out_cols if c in scored.columns]]

    @staticmethod
    def _score_to_signal(score: float) -> str:
        if score > 60:
            return "attack"    # 进攻主力
        elif score > 40:
            return "support"   # 辅助配置
        elif score > 20:
            return "watch"     # 观察
        else:
            return "avoid"     # 回避

    @staticmethod
    def _safe_col(df: pd.DataFrame, col: str):
        if col in df.columns:
            return df[col].fillna(0)
        return 0.0

    def allocate_weights(self, ranked: pd.DataFrame, total_sector_weight: float,
                         max_single: float = 0.30,
                         min_sectors: int = 3, max_sectors: int = 5) -> Dict[str, float]:
        """根据排名分配行业仓位权重。

        Args:
            ranked: rank()输出
            total_sector_weight: 行业部分总权重
            max_single: 单品种上限
            min_sectors/max_sectors: 行业数量约束

        Returns:
            Dict[code, weight]
        """
        if ranked.empty or total_sector_weight <= 0:
            return {}

        # 只选attack和support
        eligible = ranked[ranked["signal"].isin(["attack", "support"])].copy()
        if len(eligible) < min_sectors:
            # 不够则纳入watch
            watch = ranked[ranked["signal"] == "watch"].head(min_sectors - len(eligible))
            eligible = pd.concat([eligible, watch], ignore_index=True)

        # 限制最大数量
        eligible = eligible.head(max_sectors)

        if eligible.empty:
            return {}

        # 按评分加权
        weight_map = {"attack": 3.0, "support": 1.5, "watch": 0.5}
        eligible["raw_weight"] = eligible["signal"].map(weight_map).fillna(0.5)

        total_raw = eligible["raw_weight"].sum()
        if total_raw <= 0:
            return {}

        result = {}
        for _, row in eligible.iterrows():
            w = (row["raw_weight"] / total_raw) * total_sector_weight
            w = min(w, max_single)
            result[str(row["code"])] = round(float(w), 4)

        return result
