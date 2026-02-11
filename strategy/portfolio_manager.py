"""组合管理器（v2.0）。

整合信号层目标权重和风控引擎，生成调仓指令：
- 目标权重→交易指令
- 最小调仓门槛过滤
- 交易成本计算
- 与RiskControl联动
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from config.strategy_config import BACKTEST_CONFIG, RISK_CONFIG, SIGNAL_CONFIG
from strategy.risk_control import RiskControl, StopSignal


@dataclass
class Position:
    code: str
    quantity: float
    avg_cost: float


@dataclass
class TradeInstruction:
    code: str
    direction: str       # "buy" | "sell"
    target_weight: float
    current_weight: float
    delta_weight: float
    target_quantity: float = 0.0
    trade_quantity: float = 0.0
    price: float = 0.0
    amount: float = 0.0
    reason: str = ""


class PortfolioManager:
    """负责目标仓位生成和交易指令输出（v2.0）。"""

    def __init__(self, initial_capital: float = 500_000,
                 risk_config: Optional[Dict] = None,
                 signal_config: Optional[Dict] = None):
        self.cash = float(initial_capital)
        self.initial_capital = float(initial_capital)
        self.positions: Dict[str, Position] = {}
        self.total_value = float(initial_capital)
        self.peak_value = float(initial_capital)

        cfg = risk_config or RISK_CONFIG
        sig_cfg = signal_config or SIGNAL_CONFIG
        self.max_single_position = cfg.get("max_single_position", 0.30)
        self.min_trade_threshold = sig_cfg.get("min_trade_threshold", 0.05)
        self.commission_rate = BACKTEST_CONFIG.get("commission_rate", 0.0003)
        self.slippage_rate = BACKTEST_CONFIG.get("slippage_rate", 0.001)

        # 风控引擎
        self.risk_engine = RiskControl(risk_config)
        self.risk_engine.init_portfolio(initial_capital)

    # ── 查询接口 ──

    def get_current_holdings(self) -> Dict[str, float]:
        """返回当前持仓权重 {code: weight}。"""
        if self.total_value <= 0:
            return {}
        return {
            code: (pos.quantity * pos.avg_cost) / self.total_value
            for code, pos in self.positions.items()
            if pos.quantity > 0
        }

    def get_position_value(self, code: str, price: float) -> float:
        pos = self.positions.get(code)
        if pos is None:
            return 0.0
        return pos.quantity * price

    # ── 核心调仓流程 ──

    def rebalance(self, target_weights: Dict[str, float],
                  prices: Dict[str, float],
                  reason: str = "signal") -> List[TradeInstruction]:
        """根据目标权重生成交易指令。

        Args:
            target_weights: {code: target_weight}（总和应<=1）
            prices: 最新价格
            reason: 调仓原因备注

        Returns:
            List[TradeInstruction]
        """
        # 1. 更新总资产
        self.mark_to_market(prices)

        # 2. 计算当前持仓权重
        current_weights = {}
        for code, pos in self.positions.items():
            if code in prices and pos.quantity > 0:
                current_weights[code] = (pos.quantity * prices[code]) / self.total_value
            elif pos.quantity > 0:
                current_weights[code] = (pos.quantity * pos.avg_cost) / self.total_value

        # 3. 生成交易指令
        all_codes = set(list(target_weights.keys()) + list(current_weights.keys()))
        trades: List[TradeInstruction] = []

        for code in all_codes:
            tw = target_weights.get(code, 0.0)
            cw = current_weights.get(code, 0.0)
            delta = tw - cw

            # 最小门槛过滤
            if abs(delta) < self.min_trade_threshold:
                continue

            # 单品种上限
            tw = min(tw, self.max_single_position)

            price = prices.get(code, 0)
            if price <= 0:
                continue

            target_value = tw * self.total_value
            current_value = cw * self.total_value
            trade_value = target_value - current_value
            trade_qty = trade_value / price

            # ETF最小交易单位100份
            trade_qty = round(trade_qty / 100) * 100
            if abs(trade_qty) < 100:
                continue

            direction = "buy" if trade_qty > 0 else "sell"

            trades.append(TradeInstruction(
                code=code,
                direction=direction,
                target_weight=tw,
                current_weight=cw,
                delta_weight=delta,
                target_quantity=target_value / price,
                trade_quantity=abs(trade_qty),
                price=price,
                amount=abs(trade_qty * price),
                reason=reason,
            ))

        # 先卖后买排序
        trades.sort(key=lambda t: (0 if t.direction == "sell" else 1, -t.amount))
        return trades

    def apply_trades(self, trades: List[TradeInstruction]) -> Dict:
        """执行交易指令，更新持仓和现金。

        Returns:
            Dict with total_cost, trades_executed, etc.
        """
        total_cost = 0.0
        executed = 0

        for trade in trades:
            cost_rate = self.commission_rate + self.slippage_rate
            trade_cost = trade.amount * cost_rate

            if trade.direction == "buy":
                # 检查现金够不够
                total_needed = trade.amount + trade_cost
                if total_needed > self.cash:
                    # 缩减到能买的最大数量
                    max_amount = self.cash / (1 + cost_rate)
                    trade.trade_quantity = round(max_amount / trade.price / 100) * 100
                    if trade.trade_quantity <= 0:
                        continue
                    trade.amount = trade.trade_quantity * trade.price
                    trade_cost = trade.amount * cost_rate

                # 更新持仓
                if trade.code in self.positions:
                    pos = self.positions[trade.code]
                    total_qty = pos.quantity + trade.trade_quantity
                    pos.avg_cost = ((pos.avg_cost * pos.quantity) +
                                    (trade.price * trade.trade_quantity)) / total_qty
                    pos.quantity = total_qty
                else:
                    self.positions[trade.code] = Position(
                        code=trade.code,
                        quantity=trade.trade_quantity,
                        avg_cost=trade.price
                    )
                self.cash -= (trade.amount + trade_cost)

                # 注册到风控追踪
                self.risk_engine.register_position(
                    trade.code, trade.price, trade.trade_quantity
                )

            elif trade.direction == "sell":
                if trade.code not in self.positions:
                    continue
                pos = self.positions[trade.code]
                sell_qty = min(trade.trade_quantity, pos.quantity)
                pos.quantity -= sell_qty
                self.cash += (sell_qty * trade.price - trade_cost)

                if pos.quantity <= 0:
                    del self.positions[trade.code]
                    self.risk_engine.remove_position(trade.code)

            total_cost += trade_cost
            executed += 1

        return {
            "total_cost": total_cost,
            "trades_executed": executed,
            "cash_remaining": self.cash,
        }

    def mark_to_market(self, prices: Dict[str, float]) -> float:
        """按最新价格更新组合总资产。"""
        position_value = sum(
            pos.quantity * prices.get(code, pos.avg_cost)
            for code, pos in self.positions.items()
        )
        self.total_value = self.cash + position_value
        if self.total_value > self.peak_value:
            self.peak_value = self.total_value
        return self.total_value

    # ── 风控联动 ──

    def check_risk(self, prices: Dict[str, float]) -> List[StopSignal]:
        """执行风控检查，返回触发的止损/止盈信号。"""
        self.mark_to_market(prices)
        return self.risk_engine.check_all(self.total_value, prices)

    def execute_stop_signals(self, signals: List[StopSignal],
                             prices: Dict[str, float]) -> List[TradeInstruction]:
        """将止损信号转化为卖出指令。"""
        trades: List[TradeInstruction] = []

        for sig in signals:
            if sig.action == "cooldown":
                continue

            if sig.code == "PORTFOLIO":
                if sig.action == "portfolio_exit":
                    # 全部清仓
                    for code, pos in list(self.positions.items()):
                        if pos.quantity > 0 and code in prices:
                            trades.append(TradeInstruction(
                                code=code, direction="sell",
                                target_weight=0.0,
                                current_weight=pos.quantity * prices[code] / self.total_value,
                                delta_weight=-(pos.quantity * prices[code] / self.total_value),
                                trade_quantity=pos.quantity,
                                price=prices[code],
                                amount=pos.quantity * prices[code],
                                reason=sig.reason,
                            ))
                elif sig.action == "portfolio_reduce":
                    # 降至30%仓位
                    target_ratio = 0.30
                    current_pos_ratio = 1.0 - (self.cash / self.total_value)
                    if current_pos_ratio > target_ratio:
                        reduce_factor = target_ratio / max(current_pos_ratio, 0.01)
                        for code, pos in list(self.positions.items()):
                            if pos.quantity > 0 and code in prices:
                                sell_qty = round(pos.quantity * (1 - reduce_factor) / 100) * 100
                                if sell_qty >= 100:
                                    trades.append(TradeInstruction(
                                        code=code, direction="sell",
                                        target_weight=0.0, current_weight=0.0,
                                        delta_weight=0.0,
                                        trade_quantity=sell_qty,
                                        price=prices[code],
                                        amount=sell_qty * prices[code],
                                        reason=sig.reason,
                                    ))
            else:
                # 个股止损/止盈
                if sig.code in self.positions and sig.code in prices:
                    pos = self.positions[sig.code]
                    if pos.quantity > 0:
                        trades.append(TradeInstruction(
                            code=sig.code, direction="sell",
                            target_weight=0.0,
                            current_weight=pos.quantity * prices[sig.code] / self.total_value,
                            delta_weight=0.0,
                            trade_quantity=pos.quantity,
                            price=prices[sig.code],
                            amount=pos.quantity * prices[sig.code],
                            reason=sig.reason,
                        ))

        return trades

    @property
    def portfolio_summary(self) -> Dict:
        return {
            "total_value": self.total_value,
            "cash": self.cash,
            "positions": len(self.positions),
            "peak_value": self.peak_value,
            "drawdown": (self.peak_value - self.total_value) / self.peak_value if self.peak_value > 0 else 0,
            "return_pct": (self.total_value / self.initial_capital - 1) if self.initial_capital > 0 else 0,
        }
