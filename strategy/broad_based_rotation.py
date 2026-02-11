"""第二层：宽基轮动评分（v2.0）。

PRD 2.3 第二层要求:
- 4因子: MFI(0.40), MFA(0.15), PDI(0.25, 取负), CMC(0.20)
- 所有因子经滚动Z-score标准化后加权合成
- 评分阈值: >40主配, 20-40次配, <0不配
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config.strategy_config import SIGNAL_CONFIG


class BroadBasedRotation:
    """计算宽基ETF评分并排序（v2.0 4因子+Z-score）。"""

    def __init__(self, weights: Optional[Dict[str, float]] = None,
                 scale_factor: Optional[float] = None):
        cfg = SIGNAL_CONFIG
        self.weights = weights or cfg["broad_weights"]
        self.scale_factor = scale_factor or cfg.get("scale_factor", 33.3)

    def rank(self, broad_snapshot: pd.DataFrame) -> pd.DataFrame:
        """对宽基ETF计算综合评分并排序。

        broad_snapshot 每行一只宽基ETF，需要的列:
        - code, name, style
        - mfi_z: 资金流强度Z-score
        - mfa_z: 资金流加速度Z-score
        - pdi_z: 折溢价行为Z-score
        - cmc_z: 多周期动量Z-score

        Returns:
            DataFrame with columns: code, name, style, score, mfi_z, mfa_z, pdi_z, cmc_z, rank, signal
        """
        if broad_snapshot.empty:
            return pd.DataFrame(
                columns=["code", "name", "style", "score",
                         "mfi_z", "mfa_z", "pdi_z", "cmc_z", "rank", "signal"]
            )

        scored = broad_snapshot.copy()

        # 提取Z-score（缺失用0）
        mfi_z = scored["mfi_z"].fillna(0) if "mfi_z" in scored.columns else 0.0
        mfa_z = scored["mfa_z"].fillna(0) if "mfa_z" in scored.columns else 0.0
        pdi_z = scored["pdi_z"].fillna(0) if "pdi_z" in scored.columns else 0.0
        cmc_z = scored["cmc_z"].fillna(0) if "cmc_z" in scored.columns else 0.0

        # 加权合成（PRD公式: PDI取负，折价+资金流入=买入信号）
        scored["score"] = (
            mfi_z * self.weights.get("mfi", 0.40)
            + mfa_z * self.weights.get("mfa", 0.15)
            + (-pdi_z) * self.weights.get("pdi", 0.25)
            + cmc_z * self.weights.get("cmc", 0.20)
        ) * self.scale_factor

        scored["score"] = scored["score"].clip(-100, 100)

        # 排序
        scored = scored.sort_values("score", ascending=False).reset_index(drop=True)
        scored["rank"] = np.arange(1, len(scored) + 1)

        # 信号标签
        scored["signal"] = scored["score"].apply(self._score_to_signal)

        # 保留关键列
        out_cols = ["code", "score", "rank", "signal"]
        for col in ["name", "style", "mfi_z", "mfa_z", "pdi_z", "cmc_z"]:
            if col in scored.columns:
                out_cols.append(col)

        return scored[[c for c in out_cols if c in scored.columns]]

    @staticmethod
    def _score_to_signal(score: float) -> str:
        """评分转信号。"""
        if score > 40:
            return "main"      # 主配
        elif score > 20:
            return "aux"       # 次配
        elif score > 0:
            return "minor"     # 可选
        else:
            return "avoid"     # 回避

    def allocate_weights(self, ranked: pd.DataFrame, total_broad_weight: float) -> Dict[str, float]:
        """根据排名分配宽基仓位权重。

        Args:
            ranked: rank()输出
            total_broad_weight: 宽基部分总权重（如0.25）

        Returns:
            Dict[code, weight]
        """
        if ranked.empty or total_broad_weight <= 0:
            return {}

        # 只配signal != "avoid"的标的
        eligible = ranked[ranked["signal"] != "avoid"].copy()
        if eligible.empty:
            return {}

        # 主配标的得到更多权重，次配得到较少
        weight_map = {"main": 3.0, "aux": 1.5, "minor": 0.5}
        eligible["raw_weight"] = eligible["signal"].map(weight_map).fillna(0.5)

        total_raw = eligible["raw_weight"].sum()
        if total_raw <= 0:
            return {}

        result = {}
        for _, row in eligible.iterrows():
            w = (row["raw_weight"] / total_raw) * total_broad_weight
            w = min(w, 0.30)  # 单品种≤30%
            result[str(row["code"])] = round(float(w), 4)

        return result
