"""三层信号生成器（v2.0）。

整合宏观、宽基、行业三层信号：
- 震荡市识别与应对（降频+提高门槛）
- 分层调仓频率控制
- 交易成本最小调仓门槛
- 从DataProcessor输出的Z-score列读取因子
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
from config.strategy_config import SIGNAL_CONFIG, RISK_CONFIG
from strategy.macro_signal import MacroSignal
from strategy.broad_based_rotation import BroadBasedRotation
from strategy.sector_rotation import SectorRotation


class SignalGenerator:
    """聚合宏观、宽基、行业三层信号（v2.0）。"""

    def __init__(self, signal_config: Optional[Dict] = None,
                 risk_config: Optional[Dict] = None):
        self.config = signal_config or SIGNAL_CONFIG
        self.risk_config = risk_config or RISK_CONFIG

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

    def generate_signals(self, date: pd.Timestamp,
                         market_data: Dict[str, pd.DataFrame]) -> Dict:
        """生成某个交易日的三层信号。

        Args:
            date: 交易日
            market_data: {etf_code: DataFrame(已含Z-score列)}

        Returns:
            Dict with keys: date, macro, broad_ranked, sector_ranked,
                           broad_weights, sector_weights, choppy_mode
        """
        snapshots = self._build_daily_snapshot(date, market_data)

        # 第一层：宏观
        macro_signal = self.macro_engine.calculate(snapshots["macro"])
        self.score_history.append(macro_signal["score"])

        # 检查震荡市
        self._update_choppy_state(macro_signal["score"], snapshots["all"])

        # 第二层：宽基
        broad_ranked = self.broad_engine.rank(snapshots["broad"])

        # 第三层：行业
        benchmark_ret_20d = self._get_benchmark_return(snapshots["all"])
        sector_ranked = self.sector_engine.rank(snapshots["sector"], benchmark_ret_20d)

        # 仓位分配
        equity_ratio = macro_signal["total_equity_ratio"]

        # 宽基:行业 = 50:50（可调，震荡市时偏向宽基）
        broad_pct = 0.50 if not self.choppy_mode else 0.60
        sector_pct = 1.0 - broad_pct

        broad_weights = self.broad_engine.allocate_weights(
            broad_ranked, equity_ratio * broad_pct
        )
        sector_weights = self.sector_engine.allocate_weights(
            sector_ranked, equity_ratio * sector_pct,
            max_single=0.15 if self.choppy_mode else 0.30,
        )

        return {
            "date": pd.Timestamp(date),
            "macro": macro_signal,
            "broad_ranked": broad_ranked.to_dict("records") if not broad_ranked.empty else [],
            "sector_ranked": sector_ranked.to_dict("records") if not sector_ranked.empty else [],
            "broad_weights": broad_weights,
            "sector_weights": sector_weights,
            "target_weights": {**broad_weights, **sector_weights},
            "total_equity_ratio": equity_ratio,
            "choppy_mode": self.choppy_mode,
        }

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
