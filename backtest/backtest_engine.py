"""回测主引擎（v2.0）。

控制时间推进，将数据层、信号层、组合管理器串联:
1. 加载数据（缓存优先 → AKShare → Mock）
2. DataProcessor 计算指标和Z-score
3. 每日推进: 止损检查 → 信号生成 → 判断是否调仓 → 执行交易
4. 记录每日快照和交易明细
5. 输出绩效报告
"""

from __future__ import annotations

import sys
import io
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config.etf_pool import get_all_etf_codes, get_broad_codes, get_sector_codes
from config.strategy_config import BACKTEST_CONFIG, SIGNAL_CONFIG, RISK_CONFIG
from data.data_fetcher import DataFetcher
from data.data_processor import DataProcessor
from strategy.signal_generator import SignalGenerator
from strategy.portfolio_manager import PortfolioManager
from backtest.trade_logger import TradeLogger
from backtest.performance import PerformanceAnalyzer
from backtest.report_generator import ReportGenerator


class BacktestEngine:
    """回测主引擎。"""

    def __init__(self, config: Optional[Dict] = None,
                 signal_config: Optional[Dict] = None,
                 risk_config: Optional[Dict] = None,
                 use_mock: bool = False,
                 data_source: Optional[str] = None,
                 tushare_token: Optional[str] = None):
        self.config = config or BACKTEST_CONFIG
        self.signal_config = signal_config or SIGNAL_CONFIG
        self.risk_config = risk_config or RISK_CONFIG
        self.use_mock = use_mock

        # 确定数据源
        if use_mock:
            source = "mock"
        elif data_source:
            source = data_source
        else:
            source = "akshare"

        # 核心组件
        self.data_fetcher = DataFetcher(
            data_source=source,
            fallback_to_mock=True,
            tushare_token=tushare_token,
        )
        self.processor = DataProcessor()
        self.signal_gen = SignalGenerator(signal_config, risk_config)
        self.portfolio = PortfolioManager(
            initial_capital=self.config.get("initial_capital", 500_000),
            risk_config=risk_config,
            signal_config=signal_config,
        )
        self.logger = TradeLogger()
        self.analyzer = PerformanceAnalyzer()

        # 状态
        self.market_data: Dict[str, pd.DataFrame] = {}
        self.trading_dates: List[pd.Timestamp] = []
        self.last_rebal_dates: Dict[str, Optional[pd.Timestamp]] = {
            "macro": None, "broad_based": None, "sector": None, "stop_loss": None,
        }
        self.prev_signals: Optional[Dict] = None

    def run(self, progress: bool = True) -> Dict:
        """执行完整回测流程。

        Returns:
            Dict with 'metrics', 'nav_series', 'trades_df', 'signals_df'
        """
        start = self.config.get("start_date", "2022-01-01")
        end = self.config.get("end_date", "2025-12-31")

        print(f"\n{'=' * 60}")
        print(f"  ETF Rotation Strategy Backtest")
        print(f"  Period: {start} ~ {end}")
        print(f"  Capital: {self.config.get('initial_capital', 500000):,.0f}")
        print(f"  Mode: {'Mock' if self.use_mock else 'AKShare + Cache'}")
        print(f"{'=' * 60}\n")

        # Step 1: 加载数据
        t0 = time.time()
        self._load_data(start, end, progress)
        print(f"\n  Data loaded: {len(self.market_data)} ETFs, "
              f"{time.time() - t0:.1f}s")

        if not self.market_data:
            print("  [ERROR] No data loaded, aborting.")
            return {"metrics": {}, "nav_series": pd.Series(), "trades_df": pd.DataFrame()}

        # Step 2: 获取交易日列表
        self._build_trading_dates(start, end)
        print(f"  Trading days: {len(self.trading_dates)}")

        if not self.trading_dates:
            print("  [ERROR] No trading days, aborting.")
            return {"metrics": {}, "nav_series": pd.Series(), "trades_df": pd.DataFrame()}

        # Step 3: 逐日回测
        t1 = time.time()
        self._run_daily_loop(progress)
        print(f"\n  Backtest completed: {time.time() - t1:.1f}s")

        # Step 4: 绩效分析
        nav_series = self.logger.get_nav_series()
        trades_df = self.logger.get_trades_df()
        signals_df = self.logger.get_signals_df()

        # 基准净值
        benchmark_nav = self._get_benchmark_nav()

        metrics = self.analyzer.analyze(nav_series, benchmark_nav, trades_df)

        # 打印报告
        print(PerformanceAnalyzer.format_report(metrics))

        # Step 5: 生成图表和HTML报告
        report_gen = ReportGenerator(output_dir=self.config.get("output_dir", "output"))
        report_outputs = report_gen.generate_all(
            nav_series=nav_series,
            benchmark_nav=benchmark_nav,
            trades_df=trades_df,
            signals_df=signals_df,
            metrics=metrics,
            logger=self.logger,
        )
        print(f"\n  Report generated:")
        for name, filepath in report_outputs.items():
            print(f"    - {name}: {filepath}")

        return {
            "metrics": metrics,
            "nav_series": nav_series,
            "trades_df": trades_df,
            "signals_df": signals_df,
            "benchmark_nav": benchmark_nav,
            "logger": self.logger,
            "report_outputs": report_outputs,
        }

    def _load_data(self, start: str, end: str, progress: bool):
        """加载并处理所有ETF数据。"""
        codes = get_all_etf_codes()
        print(f"  Loading {len(codes)} ETFs...")

        for i, code in enumerate(codes):
            if progress and i % 5 == 0:
                pct = (i / len(codes)) * 100
                print(f"\r  Loading: {pct:.0f}% ({i}/{len(codes)})", end="", flush=True)

            result = self.data_fetcher.fetch_etf_daily(code, start, end)
            if result.data is not None and not result.data.empty:
                # 处理指标
                processed = self.processor.process(result.data)
                if not processed.empty:
                    self.market_data[code] = processed

        if progress:
            print(f"\r  Loading: 100% ({len(codes)}/{len(codes)})")

    def _build_trading_dates(self, start: str, end: str):
        """从已有数据中提取交易日列表。"""
        all_dates = set()
        for code, df in self.market_data.items():
            all_dates.update(df["date"].tolist())

        all_dates = sorted(all_dates)
        start_dt = pd.Timestamp(start)
        end_dt = pd.Timestamp(end)

        self.trading_dates = [
            d for d in all_dates
            if start_dt <= d <= end_dt
        ]

    def _run_daily_loop(self, progress: bool):
        """逐日推进回测。"""
        total_days = len(self.trading_dates)

        for i, date in enumerate(self.trading_dates):
            if progress and i % 20 == 0:
                pct = (i / total_days) * 100
                print(f"\r  Backtesting: {pct:.0f}% (day {i}/{total_days})", end="", flush=True)

            prices = self._get_prices_on_date(date)
            if not prices:
                continue

            # 1. 每日止损检查
            stop_signals = self.portfolio.check_risk(prices)
            if stop_signals:
                stop_trades = self.portfolio.execute_stop_signals(stop_signals, prices)
                if stop_trades:
                    result = self.portfolio.apply_trades(stop_trades)
                    for t in stop_trades:
                        self.logger.log_trade(
                            date, t.code, t.direction, t.trade_quantity,
                            t.price, result["total_cost"] / max(len(stop_trades), 1),
                            reason=t.reason
                        )

            # 2. 生成信号
            signals = self.signal_gen.generate_signals(date, self.market_data)
            self.logger.log_signals(date, signals)

            # 3. 判断是否需要调仓（按分层频率）
            should_rebal = False
            for layer in ["macro", "broad_based", "sector"]:
                if self.signal_gen.should_rebalance(
                    date, layer, self.last_rebal_dates,
                    self.prev_signals, signals
                ):
                    should_rebal = True
                    self.last_rebal_dates[layer] = date

            # 4. 执行调仓
            if should_rebal and signals.get("target_weights"):
                # 风控冻结检查
                if not self.portfolio.risk_engine.freeze_new_buy:
                    trades = self.portfolio.rebalance(
                        signals["target_weights"], prices, reason="signal"
                    )
                    if trades:
                        result = self.portfolio.apply_trades(trades)
                        for t in trades:
                            self.logger.log_trade(
                                date, t.code, t.direction, t.trade_quantity,
                                t.price,
                                result["total_cost"] / max(len(trades), 1),
                                reason="rebalance"
                            )

            # 5. 每日快照
            self.portfolio.mark_to_market(prices)
            self.logger.log_daily_snapshot(
                date=date,
                total_value=self.portfolio.total_value,
                cash=self.portfolio.cash,
                positions=self.portfolio.get_current_holdings(),
                macro_score=signals.get("macro", {}).get("score", 0),
                regime=signals.get("macro", {}).get("regime", "neutral"),
                choppy_mode=signals.get("choppy_mode", False),
            )

            self.prev_signals = signals

        if progress:
            print(f"\r  Backtesting: 100% (day {total_days}/{total_days})")

    def _get_prices_on_date(self, date: pd.Timestamp) -> Dict[str, float]:
        """获取某日所有ETF的收盘价。"""
        prices = {}
        for code, df in self.market_data.items():
            row = df[df["date"] == date]
            if not row.empty:
                prices[code] = float(row.iloc[0]["close"])
        return prices

    def _get_benchmark_nav(self) -> pd.Series:
        """获取基准（沪深300ETF）的归一化净值。"""
        bench_code = "510300"
        if bench_code not in self.market_data:
            return pd.Series(dtype=float)

        bench_df = self.market_data[bench_code]
        bench_df = bench_df[bench_df["date"].isin(self.trading_dates)]

        if bench_df.empty:
            return pd.Series(dtype=float)

        nav = bench_df.set_index("date")["close"]
        nav = nav / nav.iloc[0]
        return nav
