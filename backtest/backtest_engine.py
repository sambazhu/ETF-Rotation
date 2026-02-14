"""回测主引擎（v2.0）。

控制时间推进，将数据层、信号层、组合管理器串联:
1. 加载数据（缓存优先 → Tushare → Mock）
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


LAYER_NAME_MAP = {
    "macro": "宏观层",
    "broad_based": "宽基层",
    "sector": "行业层",
    "stop_loss": "风控层",
}


def _fmt_pct(value: float) -> str:
    return f"{value:.2%}"


def _fmt_num(value: float, ndigits: int = 2) -> str:
    return f"{value:.{ndigits}f}"


class BacktestEngine:
    """回测主引擎。"""

    def __init__(self, config: Optional[Dict] = None,
                 signal_config: Optional[Dict] = None,
                 risk_config: Optional[Dict] = None,
                 use_mock: bool = False,
                 tushare_token: Optional[str] = None):
        self.config = config or BACKTEST_CONFIG
        self.signal_config = signal_config or SIGNAL_CONFIG
        self.risk_config = risk_config or RISK_CONFIG
        self.use_mock = use_mock

        # 核心组件
        self.data_fetcher = DataFetcher(
            fallback_to_mock=not use_mock,
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
        print(f"  ETF轮动策略回测")
        print(f"  回测区间: {start} ~ {end}")
        print(f"  初始资金: {self.config.get('initial_capital', 500000):,.0f}")
        print(f"  数据模式: {'Mock' if self.use_mock else 'Tushare Pro + Cache'}")
        print(f"{'=' * 60}\n")

        # Step 1: 加载数据
        t0 = time.time()
        self._load_data(start, end, progress)
        print(f"\n  数据加载完成: {len(self.market_data)} 只ETF, "
              f"耗时 {time.time() - t0:.1f}s")

        if not self.market_data:
            print("  [错误] 未加载到有效数据，终止回测。")
            return {"metrics": {}, "nav_series": pd.Series(), "trades_df": pd.DataFrame()}

        # Step 2: 获取交易日列表
        self._build_trading_dates(start, end)
        print(f"  交易日数量: {len(self.trading_dates)}")

        if not self.trading_dates:
            print("  [错误] 无可用交易日，终止回测。")
            return {"metrics": {}, "nav_series": pd.Series(), "trades_df": pd.DataFrame()}

        # Step 3: 逐日回测
        t1 = time.time()
        self._run_daily_loop(progress)
        print(f"\n  回测完成，耗时: {time.time() - t1:.1f}s")

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
        print(f"\n  报告已生成:")
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
        """加载并处理所有ETF数据（修复：先合并份额再处理因子，包含预热期）。"""
        codes = get_all_etf_codes()
        print(f"  Loading {len(codes)} ETFs...")

        # 计算预热期开始日期（用于Z-score计算）
        # 需要：标准化窗口(60天) + 动量计算(20天) + 缓冲 = 100天
        start_dt = pd.Timestamp(start)
        warmup_days = 100
        warmup_start = (start_dt - pd.Timedelta(days=warmup_days)).strftime("%Y-%m-%d")
        print(f"  数据预热期: {warmup_start} ~ {start} (确保因子计算准确)")

        # Step 1: 获取原始日线数据（包含预热期）
        raw_data: Dict[str, pd.DataFrame] = {}
        for i, code in enumerate(codes):
            if progress and i % 5 == 0:
                pct = (i / len(codes)) * 100
                print(f"\r  Loading: {pct:.0f}% ({i}/{len(codes)})", end="", flush=True)

            result = self.data_fetcher.fetch_etf_daily(code, warmup_start, end)
            if result.data is not None and not result.data.empty:
                raw_data[code] = result.data

        if progress:
            print(f"\r  Loading: 100% ({len(codes)}/{len(codes)})")

        # Step 2: 获取并合并份额数据（使用预热期开始日期）
        print(f"\n  合并份额数据...")
        shares_df = self.data_fetcher.fetch_shares_for_period(warmup_start, end, codes)
        if not shares_df.empty:
            raw_data = self.data_fetcher.merge_shares_into_daily(
                raw_data,
                shares_df
            )
            print(f"  合并完成: {len(shares_df)} 条份额记录")
        else:
            print("  [警告] 份额数据为空，净流入因子将失效")

        # Step 2.5: 获取并合并技术因子数据（MACD、均线等）
        print(f"\n  获取技术因子数据...")
        tech_df = self.data_fetcher.fetch_tech_factors_for_period(warmup_start, end, codes)
        if not tech_df.empty:
            raw_data = self.data_fetcher.merge_tech_factors_into_daily(
                raw_data,
                tech_df
            )
            print(f"  技术因子数据合并完成")
        else:
            print("  [警告] 技术因子数据为空，使用本地计算")

        # Step 2.6: 获取并合并净值数据（用于PDI因子计算）
        print(f"\n  获取净值数据...")
        nav_df = self.data_fetcher.fetch_nav_for_period(warmup_start, end, codes)
        if not nav_df.empty:
            raw_data = self.data_fetcher.merge_nav_into_daily(
                raw_data,
                nav_df
            )
            print(f"  净值数据合并完成")
        else:
            print("  [警告] 净值数据为空，使用收盘价作为替代")

        # Step 3: 统一处理数据（计算因子和Z-score）
        print(f"  处理因子数据...")
        for code, df in raw_data.items():
            if not df.empty:
                processed = self.processor.process(df)
                if not processed.empty:
                    self.market_data[code] = processed
        print(f"  处理完成: {len(self.market_data)} 只ETF")

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
                print(f"\r  回测中: {pct:.0f}% (第 {i}/{total_days} 天)", end="", flush=True)

            prices = self._get_prices_on_date(date)
            if not prices:
                continue

            # 1. 每日止损检查
            stop_signals = self.portfolio.check_risk(prices)
            if stop_signals:
                stop_trades = self.portfolio.execute_stop_signals(stop_signals, prices)
                if stop_trades:
                    result = self.portfolio.apply_trades(stop_trades)
                    stop_avg_cost = result["total_cost"] / max(len(stop_trades), 1)
                    for t in stop_trades:
                        self.logger.log_trade(
                            date, t.code, t.direction, t.trade_quantity,
                            t.price, stop_avg_cost,
                            reason=t.reason,
                            current_weight=t.current_weight,
                            target_weight=t.target_weight,
                            delta_weight=t.delta_weight,
                        )

            # 2. 生成信号
            signals = self.signal_gen.generate_signals(date, self.market_data)
            self.logger.log_signals(date, signals)

            # 3. 判断是否需要调仓（按分层频率）
            should_rebal = False
            triggered_layers: List[str] = []
            for layer in ["macro", "broad_based", "sector"]:
                if self.signal_gen.should_rebalance(
                    date, layer, self.last_rebal_dates,
                    self.prev_signals, signals
                ):
                    should_rebal = True
                    triggered_layers.append(layer)
                    self.last_rebal_dates[layer] = date

            # 4. 执行调仓
            current_weights_before = self._get_current_weights_with_prices(prices)
            target_weights = signals.get("target_weights", {})
            freeze_new_buy = bool(self.portfolio.risk_engine.freeze_new_buy)
            rebal_executed = False
            rebal_trade_count = 0
            rebal_skip_reason = ""

            if should_rebal:
                if not target_weights:
                    rebal_skip_reason = "目标仓位为空"
                elif freeze_new_buy:
                    rebal_skip_reason = "风控冻结买入"
                else:
                    trades = self.portfolio.rebalance(target_weights, prices, reason="signal")
                    if trades:
                        result = self.portfolio.apply_trades(trades)
                        rebal_executed = True
                        rebal_trade_count = len(trades)
                        avg_trade_cost = result["total_cost"] / max(len(trades), 1)
                        for t in trades:
                            self.logger.log_trade(
                                date, t.code, t.direction, t.trade_quantity,
                                t.price,
                                avg_trade_cost,
                                reason="rebalance",
                                current_weight=t.current_weight,
                                target_weight=t.target_weight,
                                delta_weight=t.delta_weight,
                            )
                    else:
                        rebal_skip_reason = "未达到最小调仓门槛"

                self.logger.log_rebalance(
                    date=date,
                    trigger_layers=triggered_layers,
                    signals=signals,
                    current_weights=current_weights_before,
                    target_weights=target_weights,
                    executed=rebal_executed,
                    trade_count=rebal_trade_count,
                    freeze_new_buy=freeze_new_buy,
                    skip_reason=rebal_skip_reason,
                )

                self._print_rebalance_details(
                    date=date,
                    triggered_layers=triggered_layers,
                    signals=signals,
                    current_weights=current_weights_before,
                    target_weights=target_weights,
                    executed=rebal_executed,
                    trade_count=rebal_trade_count,
                    skip_reason=rebal_skip_reason,
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
            print(f"\r  回测中: 100% (第 {total_days}/{total_days} 天)")

    def _get_prices_on_date(self, date: pd.Timestamp) -> Dict[str, float]:
        """获取某日所有ETF的收盘价。"""
        prices = {}
        for code, df in self.market_data.items():
            row = df[df["date"] == date]
            if not row.empty:
                prices[code] = float(row.iloc[0]["close"])
        return prices

    def _get_current_weights_with_prices(self, prices: Dict[str, float]) -> Dict[str, float]:
        if self.portfolio.total_value <= 0:
            return {}

        result = {}
        for code, pos in self.portfolio.positions.items():
            if pos.quantity <= 0:
                continue
            px = prices.get(code, pos.avg_cost)
            result[code] = (pos.quantity * px) / self.portfolio.total_value
        return result

    def _print_rebalance_details(self,
                                 date: pd.Timestamp,
                                 triggered_layers: List[str],
                                 signals: Dict,
                                 current_weights: Dict[str, float],
                                 target_weights: Dict[str, float],
                                 executed: bool,
                                 trade_count: int,
                                 skip_reason: str = ""):
        macro = signals.get("macro", {})
        split = signals.get("weight_split", {})
        layer_text = ", ".join([LAYER_NAME_MAP.get(layer, layer) for layer in triggered_layers])

        print(f"\n\n[{str(date)[:10]}] 调仓评估")
        print(f"  触发层级: {layer_text if layer_text else '无'}")
        print(
            f"  宏观评分: {_fmt_num(macro.get('score', 0.0))} "
            f"| 市场状态: {macro.get('regime', 'neutral')} "
            f"| 总权益仓位: {_fmt_pct(macro.get('total_equity_ratio', 0.0))}"
        )
        print(
            f"  目标分层仓位: 宽基 {_fmt_pct(split.get('broad_target_exposure', 0.0))} "
            f"| 行业 {_fmt_pct(split.get('sector_target_exposure', 0.0))} "
            f"| 震荡市: {signals.get('choppy_mode', False)}"
        )

        print("  宏观因子贡献:")
        print(
            f"    净流入Z={_fmt_num(macro.get('net_inflow_z', 0.0), 4)}, "
            f"贡献={_fmt_num(macro.get('net_inflow_contrib', 0.0), 4)}"
        )
        print(
            f"    流入加速度Z={_fmt_num(macro.get('flow_acceleration_z', 0.0), 4)}, "
            f"贡献={_fmt_num(macro.get('flow_acceleration_contrib', 0.0), 4)}"
        )
        print(
            f"    盘中溢价Z={_fmt_num(macro.get('intraday_premium_z', 0.0), 4)}, "
            f"贡献={_fmt_num(macro.get('intraday_premium_contrib', 0.0), 4)}"
        )
        print(
            f"    溢价率Z={_fmt_num(macro.get('premium_z', 0.0), 4)}, "
            f"贡献={_fmt_num(macro.get('premium_contrib', 0.0), 4)}"
        )
        print(
            f"    动量Z={_fmt_num(macro.get('momentum_z', 0.0), 4)}, "
            f"贡献={_fmt_num(macro.get('momentum_contrib', 0.0), 4)}"
        )

        self._print_layer_top_details("宽基轮动Top3", signals.get("broad_details", []), layer="broad")
        self._print_layer_top_details("行业轮动Top5", signals.get("sector_details", []), layer="sector")

        print("  仓位变化(当前->目标):")
        changed_codes = sorted(set(current_weights.keys()) | set(target_weights.keys()))
        for code in changed_codes:
            cur = float(current_weights.get(code, 0.0))
            tar = float(target_weights.get(code, 0.0))
            delta = tar - cur
            if abs(delta) < 1e-4:
                continue
            print(
                f"    {code}: {_fmt_pct(cur)} -> {_fmt_pct(tar)} "
                f"(变化 {_fmt_pct(delta)})"
            )

        if executed:
            print(f"  调仓执行: 是 | 成交笔数: {trade_count}")
        else:
            print(f"  调仓执行: 否 | 原因: {skip_reason or '无有效交易'}")

    def _print_layer_top_details(self, title: str, details: List[Dict], layer: str):
        if not details:
            print(f"  {title}: 无")
            return

        print(f"  {title}:")
        top_n = 3 if layer == "broad" else 5
        for item in details[:top_n]:
            code = item.get("code", "")
            name = item.get("name", "")
            score = _fmt_num(float(item.get("score", 0.0)), 4)
            signal = item.get("signal", "")
            target_weight = _fmt_pct(float(item.get("target_weight", 0.0)))
            print(
                f"    {code} {name} | 分数 {score} | 信号 {signal} | 目标仓位 {target_weight}"
            )

            factors = item.get("factors", {})
            weights = item.get("weights", {})
            contrib = item.get("contrib", {})
            factor_parts = []
            for key, z_value in factors.items():
                w_value = weights.get(key.replace("_z", ""), weights.get(key, 0.0))
                c_value = contrib.get(key.replace("_z", ""), contrib.get(key, 0.0))
                factor_parts.append(
                    f"{key}: Z={_fmt_num(float(z_value), 3)}, w={_fmt_num(float(w_value), 3)}, c={_fmt_num(float(c_value), 3)}"
                )
            if factor_parts:
                print(f"      因子明细: {'; '.join(factor_parts)}")

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
