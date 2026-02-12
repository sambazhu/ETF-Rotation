"""交易记录与信号日志。

记录回测过程中的:
- 每笔交易（买入/卖出/止损/止盈）
- 每日信号评分（三层）
- 每日仓位快照
- 每日组合净值
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

import pandas as pd


@dataclass
class TradeRecord:
    date: pd.Timestamp
    code: str
    direction: str
    quantity: float
    price: float
    amount: float
    commission: float
    reason: str
    current_weight: float = 0.0
    target_weight: float = 0.0
    delta_weight: float = 0.0


@dataclass
class DailySnapshot:
    date: pd.Timestamp
    total_value: float
    cash: float
    position_value: float
    equity_ratio: float
    positions: Dict[str, float]
    macro_score: float = 0.0
    regime: str = "neutral"
    choppy_mode: bool = False


@dataclass
class RebalanceRecord:
    date: pd.Timestamp
    trigger_layers: str
    macro_score: float
    regime: str
    choppy_mode: bool
    equity_ratio: float
    broad_target_exposure: float
    sector_target_exposure: float
    broad_target_count: int
    sector_target_count: int
    executed: bool
    trade_count: int
    freeze_new_buy: bool
    skip_reason: str = ""
    current_weights: Dict[str, float] = field(default_factory=dict)
    target_weights: Dict[str, float] = field(default_factory=dict)
    weight_deltas: Dict[str, float] = field(default_factory=dict)
    broad_top: List[Dict[str, Any]] = field(default_factory=list)
    sector_top: List[Dict[str, Any]] = field(default_factory=list)


class TradeLogger:
    def __init__(self):
        self.trades: List[TradeRecord] = []
        self.daily_snapshots: List[DailySnapshot] = []
        self.signal_history: List[Dict] = []
        self.rebalance_history: List[RebalanceRecord] = []

    @staticmethod
    def _json_dumps(data: Any) -> str:
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _direction_to_cn(direction: str) -> str:
        mapping = {"buy": "\u4e70\u5165", "sell": "\u5356\u51fa"}
        return mapping.get(direction, direction)

    @staticmethod
    def _reason_to_cn(reason: str) -> str:
        mapping = {
            "signal": "\u4fe1\u53f7\u89e6\u53d1",
            "rebalance": "\u8c03\u4ed3",
            "stop_loss": "\u6b62\u635f",
            "profit_lock": "\u6b62\u76c8\u4fdd\u62a4",
            "portfolio_exit": "\u7ec4\u5408\u6e05\u4ed3",
            "portfolio_reduce": "\u7ec4\u5408\u964d\u4ed3",
        }
        return mapping.get(reason, reason)

    @staticmethod
    def _regime_to_cn(regime: str) -> str:
        mapping = {
            "bullish": "\u504f\u591a",
            "bearish": "\u504f\u7a7a",
            "neutral": "\u4e2d\u6027",
        }
        return mapping.get(regime, regime)

    def log_trade(self, date: pd.Timestamp, code: str, direction: str,
                  quantity: float, price: float, commission: float = 0.0,
                  reason: str = "signal",
                  current_weight: float = 0.0,
                  target_weight: float = 0.0,
                  delta_weight: float = 0.0):
        self.trades.append(TradeRecord(
            date=date,
            code=code,
            direction=direction,
            quantity=quantity,
            price=price,
            amount=quantity * price,
            commission=commission,
            reason=reason,
            current_weight=current_weight,
            target_weight=target_weight,
            delta_weight=delta_weight,
        ))

    def log_daily_snapshot(self, date: pd.Timestamp, total_value: float,
                           cash: float, positions: Dict[str, float],
                           macro_score: float = 0.0, regime: str = "neutral",
                           choppy_mode: bool = False):
        position_value = total_value - cash
        equity_ratio = position_value / total_value if total_value > 0 else 0
        self.daily_snapshots.append(DailySnapshot(
            date=date,
            total_value=total_value,
            cash=cash,
            position_value=position_value,
            equity_ratio=equity_ratio,
            positions=positions,
            macro_score=macro_score,
            regime=regime,
            choppy_mode=choppy_mode,
        ))

    def log_signals(self, date: pd.Timestamp, signals: Dict):
        entry = {"date": date}
        macro = signals.get("macro", {})
        weight_split = signals.get("weight_split", {})

        entry["macro_score"] = macro.get("score", 0)
        entry["equity_ratio"] = macro.get("total_equity_ratio", 0)
        entry["regime"] = macro.get("regime", "neutral")
        entry["choppy_mode"] = signals.get("choppy_mode", False)
        entry["n_broad_targets"] = len(signals.get("broad_weights", {}))
        entry["n_sector_targets"] = len(signals.get("sector_weights", {}))

        entry["\u5b8f\u89c2\u8bc4\u5206"] = macro.get("score", 0)
        entry["\u603b\u6743\u76ca\u4ed3\u4f4d"] = macro.get("total_equity_ratio", 0)
        entry["\u5e02\u573a\u72b6\u6001"] = self._regime_to_cn(macro.get("regime", "neutral"))
        entry["\u9707\u8361\u5e02"] = signals.get("choppy_mode", False)
        entry["\u5bbd\u57fa\u76ee\u6807\u4ed3\u4f4d"] = weight_split.get("broad_target_exposure", 0)
        entry["\u884c\u4e1a\u76ee\u6807\u4ed3\u4f4d"] = weight_split.get("sector_target_exposure", 0)
        entry["\u5bbd\u57fa\u6807\u7684\u6570"] = len(signals.get("broad_weights", {}))
        entry["\u884c\u4e1a\u6807\u7684\u6570"] = len(signals.get("sector_weights", {}))

        entry["\u5b8f\u89c2_\u51c0\u6d41\u5165Z"] = macro.get("net_inflow_z", 0)
        entry["\u5b8f\u89c2_\u6d41\u5165\u52a0\u901f\u5ea6Z"] = macro.get("flow_acceleration_z", 0)
        entry["\u5b8f\u89c2_\u76d8\u4e2d\u6ea2\u4ef7Z"] = macro.get("intraday_premium_z", 0)
        entry["\u5b8f\u89c2_\u6ea2\u4ef7\u7387Z"] = macro.get("premium_z", 0)
        entry["\u5b8f\u89c2_\u52a8\u91cfZ"] = macro.get("momentum_z", 0)
        entry["\u5b8f\u89c2_\u51c0\u6d41\u5165\u8d21\u732e"] = macro.get("net_inflow_contrib", 0)
        entry["\u5b8f\u89c2_\u6d41\u5165\u52a0\u901f\u5ea6\u8d21\u732e"] = macro.get("flow_acceleration_contrib", 0)
        entry["\u5b8f\u89c2_\u76d8\u4e2d\u6ea2\u4ef7\u8d21\u732e"] = macro.get("intraday_premium_contrib", 0)
        entry["\u5b8f\u89c2_\u6ea2\u4ef7\u7387\u8d21\u732e"] = macro.get("premium_contrib", 0)
        entry["\u5b8f\u89c2_\u52a8\u91cf\u8d21\u732e"] = macro.get("momentum_contrib", 0)

        entry["\u5bbd\u57fa\u5019\u9009\u660e\u7ec6"] = self._json_dumps(signals.get("broad_details", []))
        entry["\u884c\u4e1a\u5019\u9009\u660e\u7ec6"] = self._json_dumps(signals.get("sector_details", []))
        entry["\u5bbd\u57fa\u76ee\u6807\u660e\u7ec6"] = self._json_dumps(signals.get("broad_target_details", []))
        entry["\u884c\u4e1a\u76ee\u6807\u660e\u7ec6"] = self._json_dumps(signals.get("sector_target_details", []))
        entry["\u76ee\u6807\u4ed3\u4f4d\u660e\u7ec6"] = self._json_dumps(signals.get("target_weights", {}))

        self.signal_history.append(entry)

    def log_rebalance(self,
                      date: pd.Timestamp,
                      trigger_layers: List[str],
                      signals: Dict,
                      current_weights: Dict[str, float],
                      target_weights: Dict[str, float],
                      executed: bool,
                      trade_count: int,
                      freeze_new_buy: bool = False,
                      skip_reason: str = ""):
        macro = signals.get("macro", {})
        split = signals.get("weight_split", {})

        all_codes = set(current_weights.keys()) | set(target_weights.keys())
        weight_deltas = {
            code: round(float(target_weights.get(code, 0.0) - current_weights.get(code, 0.0)), 4)
            for code in sorted(all_codes)
        }

        self.rebalance_history.append(RebalanceRecord(
            date=date,
            trigger_layers="/".join(trigger_layers),
            macro_score=float(macro.get("score", 0.0)),
            regime=macro.get("regime", "neutral"),
            choppy_mode=bool(signals.get("choppy_mode", False)),
            equity_ratio=float(macro.get("total_equity_ratio", 0.0)),
            broad_target_exposure=float(split.get("broad_target_exposure", 0.0)),
            sector_target_exposure=float(split.get("sector_target_exposure", 0.0)),
            broad_target_count=len(signals.get("broad_weights", {})),
            sector_target_count=len(signals.get("sector_weights", {})),
            executed=executed,
            trade_count=int(trade_count),
            freeze_new_buy=freeze_new_buy,
            skip_reason=skip_reason,
            current_weights=current_weights,
            target_weights=target_weights,
            weight_deltas=weight_deltas,
            broad_top=signals.get("broad_details", []),
            sector_top=signals.get("sector_details", []),
        ))

    def get_trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame(columns=[
                "date", "code", "direction", "quantity", "price", "amount",
                "commission", "reason", "current_weight", "target_weight",
                "delta_weight", "direction_cn", "reason_cn",
            ])

        records = [
            {
                "date": t.date,
                "code": t.code,
                "direction": t.direction,
                "quantity": t.quantity,
                "price": t.price,
                "amount": t.amount,
                "commission": t.commission,
                "reason": t.reason,
                "current_weight": t.current_weight,
                "target_weight": t.target_weight,
                "delta_weight": t.delta_weight,
                "direction_cn": self._direction_to_cn(t.direction),
                "reason_cn": self._reason_to_cn(t.reason),
            }
            for t in self.trades
        ]
        return pd.DataFrame(records)

    def get_nav_series(self) -> pd.Series:
        if not self.daily_snapshots:
            return pd.Series(dtype=float)
        dates = [s.date for s in self.daily_snapshots]
        values = [s.total_value for s in self.daily_snapshots]
        nav = pd.Series(values, index=dates)
        if nav.iloc[0] > 0:
            nav = nav / nav.iloc[0]
        return nav

    def get_equity_ratio_series(self) -> pd.Series:
        if not self.daily_snapshots:
            return pd.Series(dtype=float)
        return pd.Series(
            [s.equity_ratio for s in self.daily_snapshots],
            index=[s.date for s in self.daily_snapshots],
        )

    def get_signals_df(self) -> pd.DataFrame:
        if not self.signal_history:
            return pd.DataFrame()
        return pd.DataFrame(self.signal_history)

    def get_rebalances_df(self) -> pd.DataFrame:
        if not self.rebalance_history:
            return pd.DataFrame(columns=[
                "date", "trigger_layers", "macro_score", "regime", "choppy_mode",
                "equity_ratio", "broad_target_exposure", "sector_target_exposure",
                "broad_target_count", "sector_target_count", "executed", "trade_count",
                "freeze_new_buy", "skip_reason", "current_weights", "target_weights",
                "weight_deltas", "broad_top", "sector_top",
            ])

        records = []
        for item in self.rebalance_history:
            records.append({
                "date": item.date,
                "trigger_layers": item.trigger_layers,
                "macro_score": item.macro_score,
                "regime": item.regime,
                "choppy_mode": item.choppy_mode,
                "equity_ratio": item.equity_ratio,
                "broad_target_exposure": item.broad_target_exposure,
                "sector_target_exposure": item.sector_target_exposure,
                "broad_target_count": item.broad_target_count,
                "sector_target_count": item.sector_target_count,
                "executed": item.executed,
                "trade_count": item.trade_count,
                "freeze_new_buy": item.freeze_new_buy,
                "skip_reason": item.skip_reason,
                "current_weights": self._json_dumps(item.current_weights),
                "target_weights": self._json_dumps(item.target_weights),
                "weight_deltas": self._json_dumps(item.weight_deltas),
                "broad_top": self._json_dumps(item.broad_top),
                "sector_top": self._json_dumps(item.sector_top),
                "\u8c03\u4ed3\u5c42\u7ea7": item.trigger_layers,
                "\u5b8f\u89c2\u8bc4\u5206": item.macro_score,
                "\u5e02\u573a\u72b6\u6001": self._regime_to_cn(item.regime),
                "\u603b\u6743\u76ca\u4ed3\u4f4d": item.equity_ratio,
                "\u5bbd\u57fa\u76ee\u6807\u4ed3\u4f4d": item.broad_target_exposure,
                "\u884c\u4e1a\u76ee\u6807\u4ed3\u4f4d": item.sector_target_exposure,
                "\u662f\u5426\u6267\u884c": item.executed,
                "\u6210\u4ea4\u7b14\u6570": item.trade_count,
                "\u5f53\u524d\u4ed3\u4f4d\u660e\u7ec6": self._json_dumps(item.current_weights),
                "\u76ee\u6807\u4ed3\u4f4d\u660e\u7ec6": self._json_dumps(item.target_weights),
                "\u4ed3\u4f4d\u53d8\u5316\u660e\u7ec6": self._json_dumps(item.weight_deltas),
                "\u5bbd\u57fa\u56e0\u5b50\u660e\u7ec6": self._json_dumps(item.broad_top),
                "\u884c\u4e1a\u56e0\u5b50\u660e\u7ec6": self._json_dumps(item.sector_top),
            })

        return pd.DataFrame(records)

    def get_positions_df(self) -> pd.DataFrame:
        if not self.daily_snapshots:
            return pd.DataFrame(columns=[
                "date", "total_value", "cash", "position_value", "equity_ratio",
                "macro_score", "regime", "choppy_mode", "positions",
            ])

        records = []
        for item in self.daily_snapshots:
            records.append({
                "date": item.date,
                "total_value": item.total_value,
                "cash": item.cash,
                "position_value": item.position_value,
                "equity_ratio": item.equity_ratio,
                "macro_score": item.macro_score,
                "regime": item.regime,
                "choppy_mode": item.choppy_mode,
                "positions": self._json_dumps(item.positions),
                "\u603b\u8d44\u4ea7": item.total_value,
                "\u73b0\u91d1": item.cash,
                "\u6301\u4ed3\u5e02\u503c": item.position_value,
                "\u6743\u76ca\u4ed3\u4f4d": item.equity_ratio,
                "\u5e02\u573a\u72b6\u6001": self._regime_to_cn(item.regime),
                "\u9707\u8361\u5e02": item.choppy_mode,
                "\u6301\u4ed3\u660e\u7ec6": self._json_dumps(item.positions),
            })
        return pd.DataFrame(records)

    @property
    def summary(self) -> Dict:
        return {
            "total_trades": len(self.trades),
            "buy_trades": sum(1 for t in self.trades if t.direction == "buy"),
            "sell_trades": sum(1 for t in self.trades if t.direction == "sell"),
            "total_commission": sum(t.commission for t in self.trades),
            "trading_days": len(self.daily_snapshots),
            "signal_days": len(self.signal_history),
            "rebalance_days": len(self.rebalance_history),
        }
