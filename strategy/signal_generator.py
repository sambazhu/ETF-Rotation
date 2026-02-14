"""三层信号生成器（v2.1）。

整合宏观、宽基、行业三层信号：
- 风格判断与自适应（新增）
- 动态因子权重调整（新增）
- 趋势择时与仓位管理（新增）
- 震荡市识别与应对
- 分层调仓频率控制
- 交易成本最小调仓门槛
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config.etf_pool import (
    BROAD_BASED_ETF_POOL,
    SECTOR_ETF_POOL,
    get_broad_codes,
    get_sector_codes,
)
from config.strategy_config import (
    SIGNAL_CONFIG,
    RISK_CONFIG,
    STYLE_CONFIG,
    DYNAMIC_WEIGHT_CONFIG,
    TIMING_CONFIG,
)
from strategy.macro_signal import MacroSignal
from strategy.broad_based_rotation import BroadBasedRotation
from strategy.sector_rotation import SectorRotation
from strategy.style_detector import StyleDetector, StyleBiasResult
from strategy.dynamic_weights import DynamicWeightAdjuster
from strategy.timing_model import TimingModel, TrendStrengthResult


def _safe_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    return float(value)


class SignalGenerator:
    """聚合宏观、宽基、行业三层信号（v2.1）

    新增功能：
    - 风格判断与自适应
    - 动态因子权重调整
    - 趋势择时与仓位管理
    """

    def __init__(self, signal_config: Optional[Dict] = None,
                 risk_config: Optional[Dict] = None):
        self.config = signal_config or SIGNAL_CONFIG
        self.risk_config = risk_config or RISK_CONFIG

        # v2.1 新增模块
        self.style_detector = StyleDetector(
            large_cap_index=STYLE_CONFIG.get("large_cap_index", "510300"),
            small_cap_index=STYLE_CONFIG.get("small_cap_index", "512100"),
            lookback_days=STYLE_CONFIG.get("lookback_days", 20),
            style_confirm_threshold=STYLE_CONFIG.get("style_confirm_threshold", 3),
            min_hold_days=STYLE_CONFIG.get("min_hold_days", 10),
        )
        self.weight_adjuster = DynamicWeightAdjuster(
            dynamic_config=DYNAMIC_WEIGHT_CONFIG
        )
        self.timing_model = TimingModel(
            timing_config=TIMING_CONFIG
        )

        # 核心引擎（使用动态权重）
        self.macro_engine = MacroSignal(
            weights=self.config["macro_weights"],
            scale_factor=self.config.get("scale_factor", 33.3),
            sigmoid_smoothing=self.config.get("sigmoid_smoothing", 15.0),
        )
        self.broad_engine = BroadBasedRotation(
            weights=self.config["broad_weights"],
            scale_factor=self.config.get("scale_factor", 33.3),
        )
        self.sector_engine = SectorRotation(
            weights=self.config["sector_weights"],
            scale_factor=self.config.get("scale_factor", 33.3),
            overheat_threshold=self.config.get("overheat_threshold", 0.15),
        )

        # 池子元数据
        self.broad_meta = pd.DataFrame(BROAD_BASED_ETF_POOL)
        self.sector_meta = pd.DataFrame(SECTOR_ETF_POOL)
        self.broad_codes = set(get_broad_codes())
        self.sector_codes = set(get_sector_codes())

        # 震荡市状态
        self.choppy_mode = False
        self.choppy_config = self.config.get("choppy_market", {})

        # 调仓成本控制
        self.min_trade_threshold = self.config.get("min_trade_threshold", 0.05)
        self.min_score_change = self.config.get("min_score_change", 15)

        # 历史评分（用于震荡市判断）
        self.score_history: List[float] = []
        self.vol_history: List[float] = []

        # v2.1 新增：缓存最新状态
        self.current_style: Optional[StyleBiasResult] = None
        self.current_trend: Optional[TrendStrengthResult] = None
        self.current_regime: str = "transitional"

    def generate_signals(self, date: pd.Timestamp,
                         market_data: Dict[str, pd.DataFrame]) -> Dict:
        """生成某个交易日的三层信号（v2.1 集成风格判断、动态权重、择时）

        Args:
            date: 交易日
            market_data: {etf_code: DataFrame(已含Z-score列)}

        Returns:
            Dict with keys: date, macro, broad_ranked, sector_ranked,
                           broad_weights, sector_weights, choppy_mode,
                           style_bias, trend_strength, market_regime  (新增)
        """
        snapshots = self._build_daily_snapshot(date, market_data)

        # ========== v2.1 新增：市场环境分析 ==========
        # 1. 风格判断
        style_bias = self.style_detector.detect_style(date, market_data)
        self.current_style = style_bias

        # 2. 趋势强度评估
        trend_strength = self.timing_model.calculate_trend_strength(date, market_data)
        self.current_trend = trend_strength

        # 3. 市场环境识别（趋势/震荡/过渡）
        market_regime = self._detect_market_regime(
            trend_strength.score,
            self.score_history[-60:] if len(self.score_history) >= 60 else self.score_history
        )
        self.current_regime = market_regime

        # 4. 动态权重调整
        dynamic_weights = self.weight_adjuster.adjust_weights(
            market_regime,
            style_bias.style,
            {
                "macro": self.config["macro_weights"].copy(),
                "broad": self.config["broad_weights"].copy(),
                "sector": self.config["sector_weights"].copy(),
            }
        )
        # 更新引擎权重
        self.macro_engine.weights = dynamic_weights["macro"]
        self.broad_engine.weights = dynamic_weights["broad"]
        self.sector_engine.weights = dynamic_weights["sector"]

        # ========== 原有信号生成逻辑 ==========
        # 第一层：宏观
        macro_signal = self.macro_engine.calculate(snapshots["macro"])
        self.score_history.append(macro_signal["score"])

        # 检查震荡市（v2.1：使用趋势强度辅助判断）
        self._update_choppy_state(macro_signal["score"], snapshots["all"])

        # 第二层：宽基（v2.1：根据风格调整）
        broad_ranked = self.broad_engine.rank(snapshots["broad"])
        # 应用风格调整
        broad_ranked = self._apply_style_adjustment(broad_ranked, style_bias)

        # 第三层：行业
        benchmark_ret_20d = self._get_benchmark_return(snapshots["all"])
        sector_ranked = self.sector_engine.rank(snapshots["sector"], benchmark_ret_20d)

        # ========== v2.1 新增：动态仓位分配 ==========
        # 根据择时模型计算总权益仓位
        base_equity_ratio = macro_signal["total_equity_ratio"]
        adjusted_equity_ratio = self.timing_model.adjust_position(
            base_equity_ratio,
            trend_strength,
            style_bias
        )

        # 根据风格调整宽基/行业比例
        broad_pct = style_bias.broad_based_ratio
        sector_pct = style_bias.sector_ratio

        # 震荡市时进一步降低行业暴露
        if self.choppy_mode:
            broad_pct = min(0.7, broad_pct + 0.1)
            sector_pct = max(0.2, sector_pct - 0.1)

        broad_weights = self.broad_engine.allocate_weights(
            broad_ranked, adjusted_equity_ratio * broad_pct
        )
        sector_weights = self.sector_engine.allocate_weights(
            sector_ranked, adjusted_equity_ratio * sector_pct,
            max_single=0.15 if self.choppy_mode else 0.25,
        )

        broad_details = self._build_broad_details(broad_ranked, broad_weights)
        sector_details = self._build_sector_details(sector_ranked, sector_weights)

        broad_target_exposure = float(sum(broad_weights.values())) if broad_weights else 0.0
        sector_target_exposure = float(sum(sector_weights.values())) if sector_weights else 0.0

        return {
            "date": pd.Timestamp(date),
            "macro": macro_signal,
            "broad_ranked": broad_ranked.to_dict("records") if not broad_ranked.empty else [],
            "sector_ranked": sector_ranked.to_dict("records") if not sector_ranked.empty else [],
            "broad_weights": broad_weights,
            "sector_weights": sector_weights,
            "target_weights": {**broad_weights, **sector_weights},
            "total_equity_ratio": adjusted_equity_ratio,
            "base_equity_ratio": base_equity_ratio,  # 原始宏观仓位
            "weight_split": {
                "broad_pct": broad_pct,
                "sector_pct": sector_pct,
                "broad_target_exposure": broad_target_exposure,
                "sector_target_exposure": sector_target_exposure,
            },
            "broad_details": broad_details,
            "sector_details": sector_details,
            "broad_target_details": [item for item in broad_details if item.get("target_weight", 0) > 0],
            "sector_target_details": [item for item in sector_details if item.get("target_weight", 0) > 0],
            "choppy_mode": self.choppy_mode,
            # v2.1 新增字段
            "style_bias": {
                "style": style_bias.style,
                "confidence": style_bias.confidence,
                "large_cap_focus": style_bias.large_cap_focus,
                "preferred_broad": style_bias.preferred_broad,
            },
            "trend_strength": {
                "score": trend_strength.score,
                "regime": trend_strength.regime,
                "recommended_position": trend_strength.recommended_position,
                "components": trend_strength.components,
            },
            "market_regime": market_regime,
            "dynamic_weights": dynamic_weights,
        }

    def _build_broad_details(self, ranked: pd.DataFrame, target_weights: Dict[str, float]) -> List[Dict]:
        if ranked is None or ranked.empty:
            return []

        details = []
        for _, row in ranked.head(10).iterrows():
            code = str(row.get("code", ""))
            details.append({
                "code": code,
                "name": row.get("name", ""),
                "style": row.get("style", ""),
                "rank": int(_safe_float(row.get("rank", 0))),
                "signal": row.get("signal", ""),
                "score": round(_safe_float(row.get("score", 0)), 4),
                "target_weight": round(_safe_float(target_weights.get(code, 0.0)), 4),
                "factors": {
                    "mfi_z": round(_safe_float(row.get("mfi_z", 0)), 4),
                    "mfa_z": round(_safe_float(row.get("mfa_z", 0)), 4),
                    "pdi_z": round(_safe_float(row.get("pdi_z", 0)), 4),
                    "cmc_z": round(_safe_float(row.get("cmc_z", 0)), 4),
                },
                "weights": {
                    "mfi": round(_safe_float(row.get("mfi_weight", 0)), 4),
                    "mfa": round(_safe_float(row.get("mfa_weight", 0)), 4),
                    "pdi": round(_safe_float(row.get("pdi_weight", 0)), 4),
                    "cmc": round(_safe_float(row.get("cmc_weight", 0)), 4),
                },
                "contrib": {
                    "mfi": round(_safe_float(row.get("mfi_contrib", 0)), 4),
                    "mfa": round(_safe_float(row.get("mfa_contrib", 0)), 4),
                    "pdi": round(_safe_float(row.get("pdi_contrib", 0)), 4),
                    "cmc": round(_safe_float(row.get("cmc_contrib", 0)), 4),
                },
            })

        return details

    def _build_sector_details(self, ranked: pd.DataFrame, target_weights: Dict[str, float]) -> List[Dict]:
        if ranked is None or ranked.empty:
            return []

        details = []
        for _, row in ranked.head(12).iterrows():
            code = str(row.get("code", ""))
            details.append({
                "code": code,
                "name": row.get("name", ""),
                "category": row.get("category", ""),
                "rank": int(_safe_float(row.get("rank", 0))),
                "signal": row.get("signal", ""),
                "score": round(_safe_float(row.get("score", 0)), 4),
                "target_weight": round(_safe_float(target_weights.get(code, 0.0)), 4),
                "overheat": bool(row.get("overheat", False)),
                "factors": {
                    "fund_flow_z": round(_safe_float(row.get("sector_flow_z", 0)), 4),
                    "flow_acceleration_z": round(_safe_float(row.get("accel_z", 0)), 4),
                    "intraday_premium_z": round(_safe_float(row.get("premium_z", 0)), 4),
                    "relative_momentum": round(_safe_float(row.get("rel_momentum", 0)), 4),
                    "relative_momentum_z": round(_safe_float(row.get("rel_momentum_z", 0)), 4),
                    "valuation_z": round(_safe_float(row.get("valuation_z", 0)), 4),
                },
                "weights": {
                    "fund_flow": round(_safe_float(row.get("fund_flow_weight", 0)), 4),
                    "flow_acceleration": round(_safe_float(row.get("flow_acceleration_weight", 0)), 4),
                    "intraday_premium": round(_safe_float(row.get("intraday_premium_weight", 0)), 4),
                    "relative_momentum": round(_safe_float(row.get("relative_momentum_weight", 0)), 4),
                    "valuation": round(_safe_float(row.get("valuation_weight", 0)), 4),
                },
                "contrib": {
                    "fund_flow": round(_safe_float(row.get("fund_flow_contrib", 0)), 4),
                    "flow_acceleration": round(_safe_float(row.get("flow_acceleration_contrib", 0)), 4),
                    "intraday_premium": round(_safe_float(row.get("intraday_premium_contrib", 0)), 4),
                    "relative_momentum": round(_safe_float(row.get("relative_momentum_contrib", 0)), 4),
                    "valuation": round(_safe_float(row.get("valuation_contrib", 0)), 4),
                },
            })

        return details

    def _build_daily_snapshot(self, date: pd.Timestamp,
                              market_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """从market_data提取截止date的最新快照（每ETF一行）。"""
        rows: List[pd.DataFrame] = []
        for code, frame in market_data.items():
            if frame.empty:
                continue
            selected = frame[frame["date"] <= date]
            if selected.empty:
                continue
            row = selected.iloc[[-1]].copy()
            row["code"] = str(code)
            rows.append(row)

        if not rows:
            empty = pd.DataFrame()
            return {"all": empty, "macro": empty, "broad": empty, "sector": empty}

        snapshot = pd.concat(rows, ignore_index=True)
        snapshot["code"] = snapshot["code"].astype(str)

        # 合并元信息
        snapshot = snapshot.merge(
            self.broad_meta.rename(columns={"code": "code"}),
            on="code", how="left", suffixes=("", "_broad")
        )
        snapshot = snapshot.merge(
            self.sector_meta.rename(columns={"code": "code"}),
            on="code", how="left", suffixes=("", "_sector")
        )

        # 字段统一（避免宽基与行业元数据合并后出现name为空）
        if "name_sector" in snapshot.columns:
            snapshot["name"] = snapshot["name"].fillna(snapshot["name_sector"])
        if "category_sector" in snapshot.columns and "category" in snapshot.columns:
            snapshot["category"] = snapshot["category"].fillna(snapshot["category_sector"])
        if "style_broad" in snapshot.columns and "style" in snapshot.columns:
            snapshot["style"] = snapshot["style"].fillna(snapshot["style_broad"])

        # 分组
        broad_snapshot = snapshot[snapshot["code"].isin(self.broad_codes)].copy()
        sector_snapshot = snapshot[snapshot["code"].isin(self.sector_codes)].copy()
        macro_snapshot = broad_snapshot.copy()

        return {
            "all": snapshot,
            "macro": macro_snapshot,
            "broad": broad_snapshot,
            "sector": sector_snapshot,
        }

    def _update_choppy_state(self, macro_score: float, all_snapshot: pd.DataFrame):
        """震荡市识别: abs(宏观评分) < 10 且 近20日波动率 < 历史25分位。"""
        if all_snapshot.empty:
            return

        # 计算全市场20日波动率（使用收益率的标准差）
        if "volatility_20d" in all_snapshot.columns:
            current_vol = float(all_snapshot["volatility_20d"].median())
        else:
            current_vol = 0.0
        self.vol_history.append(current_vol)

        choppy_score_threshold = self.choppy_config.get("score_threshold", 10)
        choppy_vol_percentile = self.choppy_config.get("vol_percentile", 25)

        if len(self.vol_history) >= 20:
            vol_threshold = float(np.percentile(self.vol_history, choppy_vol_percentile))
            self.choppy_mode = (abs(macro_score) < choppy_score_threshold
                                and current_vol < vol_threshold)
        else:
            self.choppy_mode = False

    def _get_benchmark_return(self, all_snapshot: pd.DataFrame) -> float:
        """获取基准（沪深300）的20日收益作为相对动量基准。"""
        if all_snapshot.empty or "ret_20d" not in all_snapshot.columns:
            return 0.0

        bench = all_snapshot[all_snapshot["code"] == "510300"]
        if not bench.empty and pd.notna(bench.iloc[0]["ret_20d"]):
            return float(bench.iloc[0]["ret_20d"])

        # 回退: 用所有宽基的中位数
        broad_snap = all_snapshot[all_snapshot["code"].isin(self.broad_codes)]
        if not broad_snap.empty:
            return float(broad_snap["ret_20d"].median())

        return 0.0

    def should_rebalance(self, date: pd.Timestamp, layer: str,
                         last_rebal_dates: Dict[str, Optional[pd.Timestamp]],
                         prev_signals: Optional[Dict] = None,
                         curr_signals: Optional[Dict] = None) -> bool:
        """判断某层是否需要调仓。

        Args:
            date: 当前日期
            layer: "macro" | "broad_based" | "sector" | "stop_loss"
            last_rebal_dates: 各层上次调仓日期
            prev_signals/curr_signals: 用于信号触发式行业层
        """
        freq_config = self.config.get("rebalance_freq", {})
        freq = freq_config.get(layer, "daily")

        if freq == "daily":
            return True

        last = last_rebal_dates.get(layer)
        if last is None:
            return True

        days_since = (date - last).days

        if freq == "monthly":
            return days_since >= 20  # 约月频
        elif freq == "biweekly":
            return days_since >= 10  # 约双周
        elif freq == "signal_triggered":
            if prev_signals is None or curr_signals is None:
                return days_since >= 5
            return self._sector_signal_changed(prev_signals, curr_signals)

        return True

    def _sector_signal_changed(self, prev: Dict, curr: Dict) -> bool:
        """判断行业信号是否发生足够大的变化触发调仓。"""
        if not prev.get("sector_ranked") or not curr.get("sector_ranked"):
            return True

        prev_top = {r["code"]: r["score"] for r in prev["sector_ranked"][:5]}
        curr_top = {r["code"]: r["score"] for r in curr["sector_ranked"][:5]}

        # 检查前5名变化
        for code in set(prev_top) | set(curr_top):
            old_score = prev_top.get(code, 0)
            new_score = curr_top.get(code, 0)
            if abs(new_score - old_score) > self.min_score_change:
                return True

        return False

    # ========== v2.1 新增辅助方法 ==========
    def _detect_market_regime(self, trend_score: float, score_history: List[float]) -> str:
        """检测市场环境：trending, choppy, transitional"""
        if len(score_history) < 20:
            return "transitional"

        # 计算历史波动率
        recent_scores = score_history[-20:]
        score_vol = np.std(recent_scores) if len(recent_scores) > 1 else 0

        # 获取配置阈值
        vol_threshold_high = np.percentile(self.vol_history[-60:], 60) if len(self.vol_history) >= 60 else 0.02
        macro_score_abs = abs(recent_scores[-1]) if recent_scores else 0

        # 判断市场环境
        if trend_score >= 60 and macro_score_abs > 40:
            return "trending"
        elif trend_score <= 40 and macro_score_abs < 20:
            return "choppy"
        else:
            return "transitional"

    def _apply_style_adjustment(self, broad_ranked: pd.DataFrame, style_bias: StyleBiasResult) -> pd.DataFrame:
        """根据风格偏好调整宽基评分"""
        if broad_ranked.empty or style_bias.style == "neutral":
            return broad_ranked

        adjusted = broad_ranked.copy()

        # 定义大盘/小盘ETF代码
        large_cap_codes = {"510300", "159591", "159601", "510500"}  # 沪深300, 中证A50, 中证500
        small_cap_codes = {"512100", "159532", "159537", "588000", "159915"}  # 中证1000, 中证2000, 科创50, 创业板

        # 应用风格调整
        for idx, row in adjusted.iterrows():
            code = str(row.get("code", ""))

            if style_bias.style == "large_cap":
                if code in large_cap_codes:
                    adjusted.at[idx, "score"] *= 1.3  # 提升大盘评分
                elif code in small_cap_codes:
                    adjusted.at[idx, "score"] *= 0.7  # 降低小盘评分

            elif style_bias.style == "small_cap":
                if code in small_cap_codes:
                    adjusted.at[idx, "score"] *= 1.3  # 提升小盘评分
                elif code in large_cap_codes:
                    adjusted.at[idx, "score"] *= 0.7  # 降低大盘评分

        # 重新排序
        adjusted = adjusted.sort_values("score", ascending=False).reset_index(drop=True)
        adjusted["rank"] = range(1, len(adjusted) + 1)

        return adjusted
