"""回测报告生成器 - 图表 + HTML报告。

生成内容:
1. 策略净值 vs 基准曲线
2. 回撤曲线
3. 每日仓位分布
4. 月度收益热力图
5. 宏观评分与市场状态
6. 交易分布统计
7. 完整HTML报告
"""

from __future__ import annotations

import base64
import os
from io import BytesIO
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter

# 中文字体设置
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 120
plt.rcParams["savefig.dpi"] = 120


# ── 配色方案 ──
COLORS = {
    "strategy": "#2196F3",     # 蓝色
    "benchmark": "#9E9E9E",    # 灰色
    "drawdown": "#F44336",     # 红色
    "profit": "#4CAF50",       # 绿
    "loss": "#F44336",         # 红
    "buy": "#4CAF50",
    "sell": "#F44336",
    "broad": "#2196F3",
    "sector": "#FF9800",
    "cash": "#E0E0E0",
    "bullish": "#4CAF50",
    "bearish": "#F44336",
    "neutral": "#FFC107",
}


def _fig_to_base64(fig: plt.Figure) -> str:
    """将matplotlib图表转为base64字符串（用于嵌入HTML）。"""
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return b64


def _fig_to_file(fig: plt.Figure, path: str):
    """保存图表到文件。"""
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


class ReportGenerator:
    """生成回测图表和HTML报告。"""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate_all(self, nav_series: pd.Series,
                     benchmark_nav: Optional[pd.Series],
                     trades_df: pd.DataFrame,
                     signals_df: pd.DataFrame,
                     metrics: Dict,
                     logger=None,
                     save_charts: bool = True,
                     save_html: bool = True) -> Dict[str, str]:
        """生成全部图表和报告。

        Returns:
            Dict of {chart_name: file_path}
        """
        outputs = {}

        # 1. 净值曲线
        fig = self.plot_nav_curve(nav_series, benchmark_nav)
        if save_charts:
            path = os.path.join(self.output_dir, "nav_curve.png")
            _fig_to_file(fig, path)
            outputs["nav_curve"] = path
        nav_b64 = _fig_to_base64(self.plot_nav_curve(nav_series, benchmark_nav))

        # 2. 回撤曲线
        fig = self.plot_drawdown(nav_series)
        if save_charts:
            path = os.path.join(self.output_dir, "drawdown.png")
            _fig_to_file(fig, path)
            outputs["drawdown"] = path
        dd_b64 = _fig_to_base64(self.plot_drawdown(nav_series))

        # 3. 仓位分布
        pos_b64 = ""
        if logger and logger.daily_snapshots:
            fig = self.plot_position_allocation(logger)
            if save_charts:
                path = os.path.join(self.output_dir, "positions.png")
                _fig_to_file(fig, path)
                outputs["positions"] = path
            pos_b64 = _fig_to_base64(self.plot_position_allocation(logger))

        # 4. 月度收益
        monthly_b64 = ""
        if "monthly_returns" in metrics and metrics["monthly_returns"]:
            fig = self.plot_monthly_returns(metrics["monthly_returns"])
            if save_charts:
                path = os.path.join(self.output_dir, "monthly_returns.png")
                _fig_to_file(fig, path)
                outputs["monthly_returns"] = path
            monthly_b64 = _fig_to_base64(self.plot_monthly_returns(metrics["monthly_returns"]))

        # 5. 宏观评分
        macro_b64 = ""
        if not signals_df.empty and "macro_score" in signals_df.columns:
            fig = self.plot_macro_signals(signals_df)
            if save_charts:
                path = os.path.join(self.output_dir, "macro_signals.png")
                _fig_to_file(fig, path)
                outputs["macro_signals"] = path
            macro_b64 = _fig_to_base64(self.plot_macro_signals(signals_df))

        # 6. 交易统计
        trade_b64 = ""
        if not trades_df.empty:
            fig = self.plot_trade_distribution(trades_df)
            if save_charts:
                path = os.path.join(self.output_dir, "trade_stats.png")
                _fig_to_file(fig, path)
                outputs["trade_stats"] = path
            trade_b64 = _fig_to_base64(self.plot_trade_distribution(trades_df))

        # HTML报告
        if save_html:
            html_path = os.path.join(self.output_dir, "backtest_report.html")
            self._generate_html(
                html_path, metrics, trades_df, signals_df,
                nav_b64, dd_b64, pos_b64, monthly_b64, macro_b64, trade_b64
            )
            outputs["html_report"] = html_path

        return outputs

    # ── 图表方法 ──

    def plot_nav_curve(self, nav: pd.Series,
                       benchmark: Optional[pd.Series] = None) -> plt.Figure:
        """策略净值 vs 基准净值。"""
        fig, ax = plt.subplots(figsize=(12, 5))

        ax.plot(nav.index, nav.values, color=COLORS["strategy"],
                linewidth=1.8, label="策略净值", zorder=3)
        if benchmark is not None and not benchmark.empty:
            common = nav.index.intersection(benchmark.index)
            if len(common) > 0:
                ax.plot(common, benchmark.loc[common].values,
                        color=COLORS["benchmark"], linewidth=1.2,
                        label="基准(沪深300)", linestyle="--", zorder=2)

        ax.axhline(y=1.0, color="#BDBDBD", linewidth=0.8, linestyle=":")
        ax.set_title("策略净值曲线", fontsize=14, fontweight="bold")
        ax.set_ylabel("净值")
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        fig.autofmt_xdate()
        fig.tight_layout()
        return fig

    def plot_drawdown(self, nav: pd.Series) -> plt.Figure:
        """回撤曲线。"""
        fig, ax = plt.subplots(figsize=(12, 3.5))

        cummax = nav.cummax()
        drawdown = (nav - cummax) / cummax

        ax.fill_between(drawdown.index, drawdown.values, 0,
                        color=COLORS["drawdown"], alpha=0.4)
        ax.plot(drawdown.index, drawdown.values,
                color=COLORS["drawdown"], linewidth=1.0)

        ax.set_title("回撤曲线", fontsize=14, fontweight="bold")
        ax.set_ylabel("回撤")
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        fig.autofmt_xdate()
        fig.tight_layout()
        return fig

    def plot_position_allocation(self, logger) -> plt.Figure:
        """每日仓位分配（宽基/行业/现金）。"""
        from config.etf_pool import get_broad_codes, get_sector_codes
        broad_codes = set(get_broad_codes())
        sector_codes = set(get_sector_codes())

        dates = []
        broad_pcts = []
        sector_pcts = []
        cash_pcts = []

        for snap in logger.daily_snapshots:
            dates.append(snap.date)
            total = snap.total_value
            if total <= 0:
                broad_pcts.append(0)
                sector_pcts.append(0)
                cash_pcts.append(1)
                continue

            broad_w = sum(w for c, w in snap.positions.items() if c in broad_codes)
            sector_w = sum(w for c, w in snap.positions.items() if c in sector_codes)
            cash_w = snap.cash / total

            broad_pcts.append(broad_w)
            sector_pcts.append(sector_w)
            cash_pcts.append(cash_w)

        fig, ax = plt.subplots(figsize=(12, 4))
        ax.stackplot(dates,
                     [broad_pcts, sector_pcts, cash_pcts],
                     labels=["宽基", "行业", "现金"],
                     colors=[COLORS["broad"], COLORS["sector"], COLORS["cash"]],
                     alpha=0.85)

        ax.set_title("仓位分布", fontsize=14, fontweight="bold")
        ax.set_ylabel("权重")
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_ylim(0, 1)
        ax.legend(loc="upper right", fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        fig.autofmt_xdate()
        fig.tight_layout()
        return fig

    def plot_monthly_returns(self, monthly_returns: Dict[str, float]) -> plt.Figure:
        """月度收益柱状图。"""
        months = list(monthly_returns.keys())
        returns = list(monthly_returns.values())

        fig, ax = plt.subplots(figsize=(12, 4))
        colors_list = [COLORS["profit"] if r >= 0 else COLORS["loss"] for r in returns]
        ax.bar(range(len(months)), returns, color=colors_list, alpha=0.85, width=0.7)

        ax.set_title("月度收益", fontsize=14, fontweight="bold")
        ax.set_ylabel("收益率")
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.axhline(y=0, color="black", linewidth=0.8)
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels([m[-5:] for m in months], rotation=45, fontsize=8)
        ax.grid(True, alpha=0.3, axis="y")
        fig.tight_layout()
        return fig

    def plot_macro_signals(self, signals_df: pd.DataFrame) -> plt.Figure:
        """宏观评分与市场状态。"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6),
                                        gridspec_kw={"height_ratios": [3, 1]},
                                        sharex=True)

        dates = pd.to_datetime(signals_df["date"])
        scores = signals_df["macro_score"].fillna(0)

        # 评分曲线
        ax1.plot(dates, scores, color=COLORS["strategy"], linewidth=1.5)
        ax1.axhline(y=30, color=COLORS["bullish"], linewidth=0.8, linestyle="--", alpha=0.5)
        ax1.axhline(y=-30, color=COLORS["bearish"], linewidth=0.8, linestyle="--", alpha=0.5)
        ax1.axhline(y=0, color="#BDBDBD", linewidth=0.8, linestyle=":")
        ax1.fill_between(dates, scores, 0,
                         where=scores > 0, color=COLORS["bullish"], alpha=0.15)
        ax1.fill_between(dates, scores, 0,
                         where=scores < 0, color=COLORS["bearish"], alpha=0.15)
        ax1.set_title("宏观评分与市场状态", fontsize=14, fontweight="bold")
        ax1.set_ylabel("评分")
        ax1.grid(True, alpha=0.3)

        # 仓位比例
        if "equity_ratio" in signals_df.columns:
            ratios = signals_df["equity_ratio"].fillna(0.5)
            ax2.fill_between(dates, ratios, 0, color=COLORS["strategy"], alpha=0.4)
            ax2.plot(dates, ratios, color=COLORS["strategy"], linewidth=1.0)
        ax2.set_ylabel("权益仓位")
        ax2.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax2.set_ylim(0, 1)
        ax2.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        fig.tight_layout()
        return fig

    def plot_trade_distribution(self, trades_df: pd.DataFrame) -> plt.Figure:
        """交易分布统计。"""
        fig, axes = plt.subplots(1, 3, figsize=(14, 4))

        # 1. 买卖次数
        buy_count = len(trades_df[trades_df["direction"] == "buy"])
        sell_count = len(trades_df[trades_df["direction"] == "sell"])
        axes[0].bar(["买入", "卖出"], [buy_count, sell_count],
                    color=[COLORS["buy"], COLORS["sell"]], alpha=0.85)
        axes[0].set_title("交易笔数", fontsize=12, fontweight="bold")

        # 2. 按标的分布（前10）
        top_codes = trades_df["code"].value_counts().head(10)
        axes[1].barh(top_codes.index[::-1], top_codes.values[::-1],
                     color=COLORS["strategy"], alpha=0.75)
        axes[1].set_title("交易最活跃前10ETF", fontsize=12, fontweight="bold")
        axes[1].tick_params(axis="y", labelsize=8)

        # 3. 按原因分布
        reason_counts = trades_df["reason"].value_counts()
        axes[2].pie(reason_counts.values, labels=reason_counts.index,
                    autopct="%1.0f%%", startangle=90,
                    colors=["#2196F3", "#FF9800", "#4CAF50", "#F44336"][:len(reason_counts)])
        axes[2].set_title("交易原因分布", fontsize=12, fontweight="bold")

        fig.tight_layout()
        return fig

    # ── HTML 报告 ──

    def _generate_html(self, path: str, metrics: Dict,
                       trades_df: pd.DataFrame,
                       signals_df: pd.DataFrame,
                       nav_b64: str, dd_b64: str,
                       pos_b64: str, monthly_b64: str,
                       macro_b64: str, trade_b64: str):
        """生成完整HTML报告。"""
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ETF轮动策略 - 回测报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f7fa;
            color: #333;
            line-height: 1.6;
        }}
        .header {{
            background: linear-gradient(135deg, #1a237e, #283593);
            color: white;
            padding: 40px 0;
            text-align: center;
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 8px; }}
        .header p {{ opacity: 0.85; font-size: 14px; }}
        .container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin: 24px 0;
        }}
        .metric-card {{
            background: white;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            transition: transform 0.2s;
        }}
        .metric-card:hover {{ transform: translateY(-2px); }}
        .metric-card .value {{
            font-size: 28px;
            font-weight: 700;
            color: #1a237e;
        }}
        .metric-card .value.positive {{ color: #2e7d32; }}
        .metric-card .value.negative {{ color: #c62828; }}
        .metric-card .label {{
            font-size: 13px;
            color: #666;
            margin-top: 4px;
        }}

        .chart-section {{
            background: white;
            border-radius: 10px;
            padding: 24px;
            margin: 20px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        .chart-section h2 {{
            font-size: 18px;
            margin-bottom: 16px;
            color: #1a237e;
            border-bottom: 2px solid #e8eaf6;
            padding-bottom: 8px;
        }}
        .chart-section img {{
            width: 100%;
            height: auto;
            border-radius: 6px;
        }}

        .trade-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            margin-top: 12px;
        }}
        .trade-table th {{
            background: #e8eaf6;
            padding: 10px 12px;
            text-align: left;
            font-weight: 600;
            color: #1a237e;
        }}
        .trade-table td {{
            padding: 8px 12px;
            border-bottom: 1px solid #f0f0f0;
        }}
        .trade-table tr:hover {{ background: #f5f7fa; }}
        .trade-table .buy {{ color: #2e7d32; font-weight: 600; }}
        .trade-table .sell {{ color: #c62828; font-weight: 600; }}

        .footer {{
            text-align: center;
            padding: 24px;
            color: #999;
            font-size: 12px;
        }}

        @media (max-width: 768px) {{
            .metrics-grid {{ grid-template-columns: repeat(2, 1fr); }}
        }}
    </style>
</head>
<body>

<div class="header">
    <h1>ETF轮动策略</h1>
    <p>回测报告 | {metrics.get('trading_days', 0)} 个交易日 | {metrics.get('years', 0)} 年</p>
</div>

<div class="container">

    <!-- Metrics Cards -->
    <div class="metrics-grid">
        {self._metric_card("总收益率", metrics.get("total_return", 0), fmt="pct")}
        {self._metric_card("年化收益率", metrics.get("annual_return", 0), fmt="pct")}
        {self._metric_card("最大回撤", metrics.get("max_drawdown", 0), fmt="pct")}
        {self._metric_card("夏普比率", metrics.get("sharpe_ratio", 0), fmt="num")}
        {self._metric_card("卡尔马比率", metrics.get("calmar_ratio", 0), fmt="num")}
        {self._metric_card("索提诺比率", metrics.get("sortino_ratio", 0), fmt="num")}
        {self._metric_card("胜率", metrics.get("win_rate", 0), fmt="pct")}
        {self._metric_card("总交易笔数", metrics.get("total_trades", 0), fmt="int")}
    </div>

    <!-- Benchmark comparison -->
    {self._benchmark_section(metrics)}

    <!-- NAV Curve -->
    <div class="chart-section">
        <h2>策略净值曲线</h2>
        <img src="data:image/png;base64,{nav_b64}" alt="策略净值曲线">
    </div>

    <!-- Drawdown -->
    <div class="chart-section">
        <h2>回撤曲线</h2>
        <img src="data:image/png;base64,{dd_b64}" alt="回撤曲线">
    </div>

    <!-- Position Allocation -->
    {"" if not pos_b64 else f'''
    <div class="chart-section">
        <h2>仓位分布</h2>
        <img src="data:image/png;base64,{pos_b64}" alt="仓位分布">
    </div>
    '''}

    <!-- Monthly Returns -->
    {"" if not monthly_b64 else f'''
    <div class="chart-section">
        <h2>月度收益</h2>
        <img src="data:image/png;base64,{monthly_b64}" alt="月度收益">
    </div>
    '''}

    <!-- Macro Signals -->
    {"" if not macro_b64 else f'''
    <div class="chart-section">
        <h2>宏观评分与权益仓位</h2>
        <img src="data:image/png;base64,{macro_b64}" alt="宏观评分与权益仓位">
    </div>
    '''}

    <!-- Trade Distribution -->
    {"" if not trade_b64 else f'''
    <div class="chart-section">
        <h2>交易分布</h2>
        <img src="data:image/png;base64,{trade_b64}" alt="交易分布">
    </div>
    '''}

    <!-- Trade Log -->
    <div class="chart-section">
        <h2>最近交易（近50笔）</h2>
        {self._trades_table(trades_df)}
    </div>

</div>

<div class="footer">
    由ETF轮动策略回测系统生成
</div>

</body>
</html>"""

        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    @staticmethod
    def _metric_card(label: str, value, fmt: str = "num") -> str:
        if fmt == "pct":
            display = f"{value:.2%}"
            cls = "positive" if value > 0 else "negative" if value < 0 else ""
        elif fmt == "int":
            display = f"{int(value):,}"
            cls = ""
        else:
            display = f"{value:.3f}"
            cls = "positive" if value > 0 else "negative" if value < 0 else ""

        return f'''<div class="metric-card">
            <div class="value {cls}">{display}</div>
            <div class="label">{label}</div>
        </div>'''

    @staticmethod
    def _benchmark_section(metrics: Dict) -> str:
        if "benchmark_return" not in metrics:
            return ""
        return f'''
    <div class="metrics-grid" style="grid-template-columns: repeat(3, 1fr);">
        {ReportGenerator._metric_card("基准收益率", metrics.get("benchmark_return", 0), "pct")}
        {ReportGenerator._metric_card("超额收益率", metrics.get("excess_return", 0), "pct")}
        {ReportGenerator._metric_card("信息比率", metrics.get("information_ratio", 0), "num")}
    </div>'''

    @staticmethod
    def _trades_table(trades_df: pd.DataFrame) -> str:
        if trades_df.empty:
            return "<p>暂无交易记录。</p>"

        recent = trades_df.tail(50).iloc[::-1]
        rows = []
        for _, t in recent.iterrows():
            d_cls = "buy" if t["direction"] == "buy" else "sell"
            direction_cn = t.get("direction_cn", str(t["direction"]))
            reason_cn = t.get("reason_cn", str(t["reason"]))
            rows.append(f'''<tr>
                <td>{str(t["date"])[:10]}</td>
                <td>{t["code"]}</td>
                <td class="{d_cls}">{direction_cn}</td>
                <td>{t["quantity"]:,.0f}</td>
                <td>{t["price"]:.4f}</td>
                <td>{t["amount"]:,.0f}</td>
                <td>{reason_cn}</td>
            </tr>''')

        return f'''<table class="trade-table">
            <thead><tr>
                <th>日期</th><th>代码</th><th>方向</th>
                <th>数量</th><th>价格</th><th>金额</th><th>原因</th>
            </tr></thead>
            <tbody>{"".join(rows)}</tbody>
        </table>'''
