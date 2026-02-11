"""绩效评估模块。

PRD 5.3 回测输出:
- 年化收益率
- 最大回撤 (MDD)
- 夏普比率
- 卡尔马比率
- 胜率
- 盈亏比
- 月度收益分布
- 对比基准超额收益
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd


class PerformanceAnalyzer:
    """回测绩效分析器。"""

    def __init__(self, risk_free_rate: float = 0.02):
        """
        Args:
            risk_free_rate: 年化无风险利率，默认2%
        """
        self.risk_free_rate = risk_free_rate

    def analyze(self, nav_series: pd.Series,
                benchmark_series: Optional[pd.Series] = None,
                trades_df: Optional[pd.DataFrame] = None) -> Dict:
        """综合绩效分析。

        Args:
            nav_series: 策略净值序列（index=日期, value=净值，初始=1）
            benchmark_series: 基准净值序列（同长度, 初始=1）
            trades_df: 交易记录DataFrame

        Returns:
            Dict of performance metrics
        """
        if nav_series.empty or len(nav_series) < 2:
            return self._empty_result()

        result = {}

        # 基础收益指标
        result.update(self._calc_return_metrics(nav_series))

        # 风险指标
        result.update(self._calc_risk_metrics(nav_series))

        # 夏普/卡尔马
        result.update(self._calc_ratio_metrics(nav_series))

        # 交易统计
        if trades_df is not None and not trades_df.empty:
            result.update(self._calc_trade_metrics(trades_df))

        # 基准对比
        if benchmark_series is not None and not benchmark_series.empty:
            result.update(self._calc_benchmark_metrics(nav_series, benchmark_series))

        # 月度收益
        result["monthly_returns"] = self._calc_monthly_returns(nav_series)

        return result

    def _calc_return_metrics(self, nav: pd.Series) -> Dict:
        total_return = float(nav.iloc[-1] / nav.iloc[0] - 1)
        trading_days = len(nav)
        years = trading_days / 252

        if years > 0:
            annual_return = float((1 + total_return) ** (1 / years) - 1)
        else:
            annual_return = 0.0

        return {
            "total_return": total_return,
            "annual_return": annual_return,
            "trading_days": trading_days,
            "years": round(years, 2),
        }

    def _calc_risk_metrics(self, nav: pd.Series) -> Dict:
        # 日收益率
        daily_returns = nav.pct_change().dropna()

        # 最大回撤
        cummax = nav.cummax()
        drawdown = (nav - cummax) / cummax
        max_drawdown = float(drawdown.min())
        max_dd_end = drawdown.idxmin()

        # MDD开始日期（从峰值开始）
        peak_before_dd = nav[:max_dd_end].idxmax()

        # 波动率
        annual_vol = float(daily_returns.std() * np.sqrt(252))

        return {
            "max_drawdown": max_drawdown,
            "max_dd_start": str(peak_before_dd.date()) if hasattr(peak_before_dd, 'date') else str(peak_before_dd),
            "max_dd_end": str(max_dd_end.date()) if hasattr(max_dd_end, 'date') else str(max_dd_end),
            "annual_volatility": annual_vol,
            "daily_vol": float(daily_returns.std()),
        }

    def _calc_ratio_metrics(self, nav: pd.Series) -> Dict:
        daily_returns = nav.pct_change().dropna()
        annual_return = float((nav.iloc[-1] / nav.iloc[0]) ** (252 / len(nav)) - 1)
        annual_vol = float(daily_returns.std() * np.sqrt(252))

        # 夏普比率
        sharpe = (annual_return - self.risk_free_rate) / annual_vol if annual_vol > 1e-8 else 0.0

        # 卡尔马比率
        cummax = nav.cummax()
        max_dd = abs(float(((nav - cummax) / cummax).min()))
        calmar = annual_return / max_dd if max_dd > 1e-8 else 0.0

        # Sortino比率（只用下行波动率）
        downside = daily_returns[daily_returns < 0]
        downside_vol = float(downside.std() * np.sqrt(252)) if len(downside) > 0 else 1e-8
        sortino = (annual_return - self.risk_free_rate) / downside_vol if downside_vol > 1e-8 else 0.0

        return {
            "sharpe_ratio": round(sharpe, 3),
            "calmar_ratio": round(calmar, 3),
            "sortino_ratio": round(sortino, 3),
        }

    def _calc_trade_metrics(self, trades_df: pd.DataFrame) -> Dict:
        total_trades = len(trades_df)
        if total_trades == 0:
            return {"total_trades": 0}

        buy_trades = len(trades_df[trades_df["direction"] == "buy"])
        sell_trades = len(trades_df[trades_df["direction"] == "sell"])
        total_commission = float(trades_df["commission"].sum())

        # 计算胜率和盈亏比（基于完成的交易对）
        win_count = 0
        loss_count = 0
        total_profit = 0.0
        total_loss = 0.0

        # 按标的分组匹配买卖
        codes = trades_df["code"].unique()
        for code in codes:
            code_trades = trades_df[trades_df["code"] == code].sort_values("date")
            buys = code_trades[code_trades["direction"] == "buy"]
            sells = code_trades[code_trades["direction"] == "sell"]

            for _, sell in sells.iterrows():
                # 找最近的买入
                prior_buys = buys[buys["date"] <= sell["date"]]
                if prior_buys.empty:
                    continue
                avg_buy = float(prior_buys["price"].mean())
                pnl = (sell["price"] - avg_buy) * sell["quantity"]
                if pnl > 0:
                    win_count += 1
                    total_profit += pnl
                else:
                    loss_count += 1
                    total_loss += abs(pnl)

        completed = win_count + loss_count
        win_rate = win_count / completed if completed > 0 else 0.0
        profit_loss_ratio = (total_profit / win_count) / (total_loss / loss_count) if (win_count > 0 and loss_count > 0) else 0.0

        return {
            "total_trades": total_trades,
            "buy_trades": buy_trades,
            "sell_trades": sell_trades,
            "total_commission": round(total_commission, 2),
            "completed_trades": completed,
            "win_rate": round(win_rate, 4),
            "profit_loss_ratio": round(profit_loss_ratio, 3),
        }

    def _calc_benchmark_metrics(self, nav: pd.Series, bench: pd.Series) -> Dict:
        # 对齐索引
        common = nav.index.intersection(bench.index)
        if len(common) < 2:
            return {"alpha": 0.0, "excess_return": 0.0}

        s = nav.loc[common]
        b = bench.loc[common]

        strategy_return = float(s.iloc[-1] / s.iloc[0] - 1)
        bench_return = float(b.iloc[-1] / b.iloc[0] - 1)
        excess = strategy_return - bench_return

        # 信息比率
        s_daily = s.pct_change().dropna()
        b_daily = b.pct_change().dropna()
        common_daily = s_daily.index.intersection(b_daily.index)
        if len(common_daily) > 10:
            excess_daily = s_daily.loc[common_daily] - b_daily.loc[common_daily]
            tracking_error = float(excess_daily.std() * np.sqrt(252))
            info_ratio = excess / tracking_error if tracking_error > 1e-8 else 0.0
        else:
            info_ratio = 0.0

        return {
            "benchmark_return": round(bench_return, 4),
            "excess_return": round(excess, 4),
            "information_ratio": round(info_ratio, 3),
        }

    def _calc_monthly_returns(self, nav: pd.Series) -> Dict:
        if nav.empty:
            return {}
        monthly = nav.resample("ME").last()
        monthly_ret = monthly.pct_change().dropna()
        return {
            str(d.date()): round(float(r), 4)
            for d, r in monthly_ret.items()
        }

    def _empty_result(self) -> Dict:
        return {
            "total_return": 0.0, "annual_return": 0.0,
            "max_drawdown": 0.0, "sharpe_ratio": 0.0,
            "calmar_ratio": 0.0, "total_trades": 0,
        }

    @staticmethod
    def format_report(metrics: Dict) -> str:
        """格式化绩效报告为可读字符串。"""
        lines = [
            "=" * 50,
            "  Backtest Performance Report",
            "=" * 50,
            "",
            f"  Total Return:     {metrics.get('total_return', 0):.2%}",
            f"  Annual Return:    {metrics.get('annual_return', 0):.2%}",
            f"  Max Drawdown:     {metrics.get('max_drawdown', 0):.2%}",
            f"  Annual Vol:       {metrics.get('annual_volatility', 0):.2%}",
            f"  Sharpe Ratio:     {metrics.get('sharpe_ratio', 0):.3f}",
            f"  Calmar Ratio:     {metrics.get('calmar_ratio', 0):.3f}",
            f"  Sortino Ratio:    {metrics.get('sortino_ratio', 0):.3f}",
            "",
            f"  Total Trades:     {metrics.get('total_trades', 0)}",
            f"  Win Rate:         {metrics.get('win_rate', 0):.1%}",
            f"  Profit/Loss:      {metrics.get('profit_loss_ratio', 0):.2f}",
            f"  Commission:       {metrics.get('total_commission', 0):.2f}",
            "",
        ]
        if "benchmark_return" in metrics:
            lines.extend([
                f"  Benchmark Return: {metrics['benchmark_return']:.2%}",
                f"  Excess Return:    {metrics['excess_return']:.2%}",
                f"  Info Ratio:       {metrics.get('information_ratio', 0):.3f}",
                "",
            ])
        lines.append("=" * 50)
        return "\n".join(lines)
