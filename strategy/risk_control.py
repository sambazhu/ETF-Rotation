"""多层止损止盈引擎（v2.0）。

PRD 3.4 多层止损止盈体系:
- 层级1: 个股止损（追踪止损8%回撤 + 硬止损10%跌幅）
- 层级2: 组合层面（回撤5%预警/8%减仓/12%清仓+冷静期）
- 层级3: 利润保护（盈利>15%后追踪止盈8%回撤）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config.strategy_config import RISK_CONFIG


@dataclass
class PositionTracker:
    """个股持仓追踪器。"""
    code: str
    entry_price: float          # 买入均价
    current_price: float = 0.0
    peak_price: float = 0.0     # 持仓期间最高价
    quantity: float = 0.0

    @property
    def pnl_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price

    @property
    def drawdown_from_peak(self) -> float:
        if self.peak_price <= 0:
            return 0.0
        return (self.peak_price - self.current_price) / self.peak_price

    def update_price(self, price: float):
        self.current_price = price
        if price > self.peak_price:
            self.peak_price = price


@dataclass
class StopSignal:
    """止损/止盈信号。"""
    code: str
    action: str       # "stop_loss", "hard_stop", "profit_lock", "portfolio_reduce", "portfolio_exit"
    reason: str
    severity: int     # 1=预警, 2=减仓, 3=清仓


class RiskControl:
    """多层止损止盈引擎。"""

    def __init__(self, risk_config: Optional[Dict] = None):
        cfg = risk_config or RISK_CONFIG
        stop_cfg = cfg.get("stop_loss", {})

        # 层级1: 个股
        self.trailing_stop = stop_cfg.get("single_trailing_stop", 0.08)
        self.hard_stop = stop_cfg.get("single_hard_stop", 0.10)

        # 层级2: 组合
        self.portfolio_warning = stop_cfg.get("portfolio_drawdown_warning", 0.05)
        self.portfolio_reduce = stop_cfg.get("portfolio_drawdown_reduce", 0.08)
        self.portfolio_exit = stop_cfg.get("portfolio_drawdown_exit", 0.12)
        self.cooldown_days = stop_cfg.get("cooldown_days", 5)

        # 层级3: 利润保护
        self.profit_lock_threshold = stop_cfg.get("profit_lock_threshold", 0.15)
        self.profit_lock_trailing = stop_cfg.get("profit_lock_trailing", 0.08)

        # 状态
        self.trackers: Dict[str, PositionTracker] = {}
        self.portfolio_peak_value: float = 0.0
        self.initial_value: float = 0.0
        self.freeze_new_buy: bool = False
        self.cooldown_remaining: int = 0

    def init_portfolio(self, total_value: float):
        """初始化组合基准值。"""
        self.initial_value = total_value
        self.portfolio_peak_value = total_value

    def register_position(self, code: str, entry_price: float, quantity: float):
        """注册新建仓位。"""
        self.trackers[code] = PositionTracker(
            code=code, entry_price=entry_price,
            current_price=entry_price, peak_price=entry_price,
            quantity=quantity
        )

    def remove_position(self, code: str):
        """清除已平仓位。"""
        self.trackers.pop(code, None)

    def update_prices(self, prices: Dict[str, float]):
        """更新所有持仓价格。"""
        for code, tracker in self.trackers.items():
            if code in prices:
                tracker.update_price(prices[code])

    def check_all(self, total_value: float, prices: Dict[str, float]) -> List[StopSignal]:
        """执行全部止损/止盈检查。

        Args:
            total_value: 当前组合总值
            prices: 最新价格

        Returns:
            触发的信号列表
        """
        self.update_prices(prices)
        signals: List[StopSignal] = []

        # 冷静期倒计时
        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= 1
            signals.append(StopSignal(
                code="PORTFOLIO", action="cooldown",
                reason=f"冷静期剩余{self.cooldown_remaining}天", severity=1
            ))
            return signals

        # 层级1: 个股止损
        for code, tracker in list(self.trackers.items()):
            sig = self._check_single_stop(tracker)
            if sig:
                signals.append(sig)

        # 层级2: 组合层面
        portfolio_signals = self._check_portfolio_stop(total_value)
        signals.extend(portfolio_signals)

        # 层级3: 利润保护
        for code, tracker in list(self.trackers.items()):
            sig = self._check_profit_lock(tracker)
            if sig:
                signals.append(sig)

        # 更新组合峰值
        if total_value > self.portfolio_peak_value:
            self.portfolio_peak_value = total_value

        return signals

    def _check_single_stop(self, tracker: PositionTracker) -> Optional[StopSignal]:
        """层级1: 个股止损检查。"""
        # 硬止损: 从买入价下跌超阈值
        if tracker.pnl_pct < -self.hard_stop:
            return StopSignal(
                code=tracker.code, action="hard_stop",
                reason=f"硬止损: 跌幅{tracker.pnl_pct:.1%} > {self.hard_stop:.0%}",
                severity=3
            )

        # 追踪止损: 从持仓期间最高点回撤超阈值
        if tracker.drawdown_from_peak > self.trailing_stop:
            return StopSignal(
                code=tracker.code, action="trailing_stop",
                reason=f"追踪止损: 回撤{tracker.drawdown_from_peak:.1%} > {self.trailing_stop:.0%}",
                severity=3
            )

        return None

    def _check_portfolio_stop(self, total_value: float) -> List[StopSignal]:
        """层级2: 组合层面止损。"""
        signals = []

        if self.portfolio_peak_value <= 0:
            return signals

        drawdown = (self.portfolio_peak_value - total_value) / self.portfolio_peak_value

        if drawdown > self.portfolio_exit:
            signals.append(StopSignal(
                code="PORTFOLIO", action="portfolio_exit",
                reason=f"组合回撤{drawdown:.1%} > {self.portfolio_exit:.0%}, 全部清仓",
                severity=3
            ))
            self.cooldown_remaining = self.cooldown_days

        elif drawdown > self.portfolio_reduce:
            signals.append(StopSignal(
                code="PORTFOLIO", action="portfolio_reduce",
                reason=f"组合回撤{drawdown:.1%} > {self.portfolio_reduce:.0%}, 降至30%仓位",
                severity=2
            ))

        elif drawdown > self.portfolio_warning:
            signals.append(StopSignal(
                code="PORTFOLIO", action="portfolio_warning",
                reason=f"组合回撤{drawdown:.1%} > {self.portfolio_warning:.0%}, 冻结新买入",
                severity=1
            ))
            self.freeze_new_buy = True
        else:
            self.freeze_new_buy = False

        return signals

    def _check_profit_lock(self, tracker: PositionTracker) -> Optional[StopSignal]:
        """层级3: 利润保护（追踪止盈）。

        当盈利曾超过profit_lock_threshold后，如果从盈利高点回撤超过
        profit_lock_trailing，则触发利润保护。
        """
        # 计算峰值盈利百分比
        profit_peak_pct = (tracker.peak_price - tracker.entry_price) / tracker.entry_price
        if profit_peak_pct < self.profit_lock_threshold:
            return None  # 峰值盈利未达到止盈启动线

        # 已触发止盈线，检查从盈利高点的回撤
        current_profit = tracker.pnl_pct
        profit_drawdown = profit_peak_pct - current_profit

        if profit_drawdown > self.profit_lock_trailing:
            return StopSignal(
                code=tracker.code, action="profit_lock",
                reason=f"利润保护: 盈利从{profit_peak_pct:.1%}回落至{current_profit:.1%}",
                severity=2
            )

        return None

    @property
    def status_summary(self) -> Dict:
        """返回风控状态摘要。"""
        return {
            "positions_tracked": len(self.trackers),
            "portfolio_peak": self.portfolio_peak_value,
            "freeze_new_buy": self.freeze_new_buy,
            "cooldown_remaining": self.cooldown_remaining,
        }
