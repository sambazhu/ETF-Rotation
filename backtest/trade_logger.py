"""交易记录与信号日志。

记录回测过程中的:
- 每笔交易（买入/卖出/止损/止盈）
- 每日信号评分（三层）
- 每日仓位快照
- 每日组合净值
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd


@dataclass
class TradeRecord:
    """单笔交易记录。"""
    date: pd.Timestamp
    code: str
    direction: str       # buy / sell
    quantity: float
    price: float
    amount: float
    commission: float
    reason: str          # signal / stop_loss / profit_lock / rebalance


@dataclass
class DailySnapshot:
    """每日组合快照。"""
    date: pd.Timestamp
    total_value: float
    cash: float
    position_value: float
    equity_ratio: float  # 股票仓位占比
    positions: Dict[str, float]  # {code: weight}
    macro_score: float = 0.0
    regime: str = "neutral"
    choppy_mode: bool = False


class TradeLogger:
    """记录回测全流程数据。"""

    def __init__(self):
        self.trades: List[TradeRecord] = []
        self.daily_snapshots: List[DailySnapshot] = []
        self.signal_history: List[Dict] = []

    def log_trade(self, date: pd.Timestamp, code: str, direction: str,
                  quantity: float, price: float, commission: float = 0.0,
                  reason: str = "signal"):
        self.trades.append(TradeRecord(
            date=date, code=code, direction=direction,
            quantity=quantity, price=price,
            amount=quantity * price, commission=commission,
            reason=reason,
        ))

    def log_daily_snapshot(self, date: pd.Timestamp, total_value: float,
                           cash: float, positions: Dict[str, float],
                           macro_score: float = 0.0, regime: str = "neutral",
                           choppy_mode: bool = False):
        position_value = total_value - cash
        equity_ratio = position_value / total_value if total_value > 0 else 0
        self.daily_snapshots.append(DailySnapshot(
            date=date, total_value=total_value, cash=cash,
            position_value=position_value, equity_ratio=equity_ratio,
            positions=positions, macro_score=macro_score,
            regime=regime, choppy_mode=choppy_mode,
        ))

    def log_signals(self, date: pd.Timestamp, signals: Dict):
        entry = {"date": date}
        if "macro" in signals:
            entry["macro_score"] = signals["macro"].get("score", 0)
            entry["equity_ratio"] = signals["macro"].get("total_equity_ratio", 0)
            entry["regime"] = signals["macro"].get("regime", "neutral")
        entry["choppy_mode"] = signals.get("choppy_mode", False)
        entry["n_broad_targets"] = len(signals.get("broad_weights", {}))
        entry["n_sector_targets"] = len(signals.get("sector_weights", {}))
        self.signal_history.append(entry)

    # ── 导出 ──

    def get_trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame(columns=["date", "code", "direction", "quantity",
                                         "price", "amount", "commission", "reason"])
        records = [
            {
                "date": t.date, "code": t.code, "direction": t.direction,
                "quantity": t.quantity, "price": t.price,
                "amount": t.amount, "commission": t.commission,
                "reason": t.reason,
            }
            for t in self.trades
        ]
        return pd.DataFrame(records)

    def get_nav_series(self) -> pd.Series:
        """返回每日净值序列（以初始值归一）。"""
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
            index=[s.date for s in self.daily_snapshots]
        )

    def get_signals_df(self) -> pd.DataFrame:
        if not self.signal_history:
            return pd.DataFrame()
        return pd.DataFrame(self.signal_history)

    @property
    def summary(self) -> Dict:
        return {
            "total_trades": len(self.trades),
            "buy_trades": sum(1 for t in self.trades if t.direction == "buy"),
            "sell_trades": sum(1 for t in self.trades if t.direction == "sell"),
            "total_commission": sum(t.commission for t in self.trades),
            "trading_days": len(self.daily_snapshots),
            "signal_days": len(self.signal_history),
        }
