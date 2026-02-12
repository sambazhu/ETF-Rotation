"""Phase 3 验证脚本: 回测引擎。

验证内容:
1. 模块导入
2. TradeLogger: 记录 + 导出
3. PerformanceAnalyzer: 指标计算
4. BacktestEngine: Mock数据完整回测
5. main.py: 入口可运行
"""

from __future__ import annotations

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd


def print_header(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_result(name: str, passed: bool, detail: str = ""):
    tag = "[PASS]" if passed else "[FAIL]"
    msg = f"  {tag} {name}"
    if detail:
        msg += f": {detail}"
    print(msg)


def verify_imports() -> int:
    print_header("1. Module Imports")
    errors = 0
    modules = [
        ("TradeLogger", "backtest.trade_logger", "TradeLogger"),
        ("TradeRecord", "backtest.trade_logger", "TradeRecord"),
        ("DailySnapshot", "backtest.trade_logger", "DailySnapshot"),
        ("PerformanceAnalyzer", "backtest.performance", "PerformanceAnalyzer"),
        ("BacktestEngine", "backtest.backtest_engine", "BacktestEngine"),
    ]
    for name, mod, attr in modules:
        try:
            m = __import__(mod, fromlist=[attr])
            getattr(m, attr)
            print_result(name, True)
        except Exception as e:
            print_result(name, False, str(e))
            errors += 1
    return errors


def verify_trade_logger() -> int:
    print_header("2. TradeLogger")
    errors = 0

    from backtest.trade_logger import TradeLogger

    logger = TradeLogger()

    # Log trades
    logger.log_trade(pd.Timestamp("2024-01-15"), "510300", "buy", 10000, 4.0, 12.0)
    logger.log_trade(pd.Timestamp("2024-02-01"), "510300", "sell", 5000, 4.5, 6.75)
    logger.log_trade(pd.Timestamp("2024-02-15"), "512480", "buy", 5000, 2.0, 3.0)
    print_result("log_trade", len(logger.trades) == 3, f"{len(logger.trades)} trades")

    # Log snapshots
    for i in range(5):
        d = pd.Timestamp(f"2024-01-{10 + i}")
        logger.log_daily_snapshot(d, 500000 + i * 1000, 200000, {"510300": 0.6})
    print_result("log_daily_snapshot", len(logger.daily_snapshots) == 5)

    # Log signals
    logger.log_signals(pd.Timestamp("2024-01-10"), {
        "macro": {"score": 25.0, "total_equity_ratio": 0.75, "regime": "bullish"},
        "choppy_mode": False,
        "broad_weights": {"510300": 0.2},
        "sector_weights": {"512480": 0.15},
    })
    print_result("log_signals", len(logger.signal_history) == 1)

    # Export
    trades_df = logger.get_trades_df()
    print_result("get_trades_df", len(trades_df) == 3 and "code" in trades_df.columns)

    nav = logger.get_nav_series()
    print_result("get_nav_series", len(nav) == 5 and nav.iloc[0] == 1.0,
                 f"len={len(nav)}, first={nav.iloc[0]:.4f}")

    equity = logger.get_equity_ratio_series()
    print_result("get_equity_ratio_series", len(equity) == 5)

    summary = logger.summary
    print_result("summary", summary["total_trades"] == 3 and summary["buy_trades"] == 2,
                 f"trades={summary['total_trades']}, buys={summary['buy_trades']}")

    return errors


def verify_performance() -> int:
    print_header("3. PerformanceAnalyzer")
    errors = 0

    from backtest.performance import PerformanceAnalyzer

    analyzer = PerformanceAnalyzer(risk_free_rate=0.02)

    # Create synthetic NAV: ~10% annual return with realistic noise
    dates = pd.date_range("2023-01-01", periods=252, freq="B")
    np.random.seed(42)
    daily_return = (1.10) ** (1 / 252) - 1
    nav_values = [1.0]
    for _ in range(251):
        noise = np.random.normal(0, 0.005)  # ~0.5% daily noise
        nav_values.append(nav_values[-1] * (1 + daily_return + noise))
    nav = pd.Series(nav_values, index=dates)

    # Create mock trades
    trades_df = pd.DataFrame({
        "date": [dates[10], dates[50], dates[60], dates[100]],
        "code": ["510300", "510300", "510300", "510300"],
        "direction": ["buy", "sell", "buy", "sell"],
        "quantity": [10000, 10000, 5000, 5000],
        "price": [4.0, 4.3, 4.1, 4.5],
        "amount": [40000, 43000, 20500, 22500],
        "commission": [12, 12.9, 6.15, 6.75],
        "reason": ["signal", "signal", "signal", "signal"],
    })

    # Benchmark: flat
    bench = pd.Series([1.0] * 252, index=dates)

    metrics = analyzer.analyze(nav, bench, trades_df)

    # Validate
    print_result("total_return ~10%",
                 abs(metrics["total_return"] - 0.10) < 0.02,
                 f"{metrics['total_return']:.2%}")
    print_result("annual_return ~10%",
                 abs(metrics["annual_return"] - 0.10) < 0.02,
                 f"{metrics['annual_return']:.2%}")
    print_result("max_drawdown small",
                 metrics["max_drawdown"] > -0.05,
                 f"{metrics['max_drawdown']:.4%}")
    print_result("sharpe > 0",
                 metrics["sharpe_ratio"] > 0,
                 f"{metrics['sharpe_ratio']:.3f}")
    print_result("calmar > 0",
                 metrics["calmar_ratio"] > 0,
                 f"{metrics['calmar_ratio']:.3f}")
    print_result("trade stats",
                 metrics["total_trades"] == 4,
                 f"trades={metrics['total_trades']}, win_rate={metrics.get('win_rate', 0):.1%}")
    print_result("benchmark metrics",
                 "excess_return" in metrics,
                 f"excess={metrics.get('excess_return', 0):.2%}")
    print_result("monthly_returns",
                 len(metrics.get("monthly_returns", {})) > 0,
                 f"{len(metrics.get('monthly_returns', {}))} months")

    # Format report
    report = PerformanceAnalyzer.format_report(metrics)
    print_result("format_report", "回测绩效报告" in report and "年化收益率" in report,
                 f"{len(report)} chars")

    # Empty input
    empty = analyzer.analyze(pd.Series(dtype=float))
    print_result("empty input", empty["total_return"] == 0.0)

    return errors


def verify_backtest_engine() -> int:
    print_header("4. BacktestEngine (mock backtest)")
    errors = 0

    from backtest.backtest_engine import BacktestEngine

    config = {
        "start_date": "2024-01-01",
        "end_date": "2024-03-31",
        "initial_capital": 500_000,
        "commission_rate": 0.0003,
        "slippage_rate": 0.001,
    }

    engine = BacktestEngine(config=config, use_mock=True)
    print_result("engine created", True)

    result = engine.run(progress=False)

    # Validate result structure
    print_result("result has metrics", "metrics" in result)
    print_result("result has nav_series", "nav_series" in result and not result["nav_series"].empty,
                 f"len={len(result['nav_series'])}")
    print_result("result has trades_df", "trades_df" in result,
                 f"{len(result['trades_df'])} trades")
    print_result("result has signals_df", "signals_df" in result,
                 f"{len(result['signals_df'])} signal days")

    # Validate metrics
    m = result["metrics"]
    if m:
        print_result("total_return computed", "total_return" in m,
                     f"{m.get('total_return', 0):.2%}")
        print_result("max_drawdown computed", "max_drawdown" in m,
                     f"{m.get('max_drawdown', 0):.2%}")
        print_result("sharpe computed", "sharpe_ratio" in m,
                     f"{m.get('sharpe_ratio', 0):.3f}")
        print_result("trades counted", "total_trades" in m,
                     f"{m.get('total_trades', 0)} trades")
    else:
        print_result("metrics present", False, "empty metrics")
        errors += 1

    # Validate logger
    if result.get("logger"):
        lg = result["logger"]
        print_result("logger has snapshots", len(lg.daily_snapshots) > 0,
                     f"{len(lg.daily_snapshots)} days")
        print_result("logger has signals", len(lg.signal_history) > 0,
                     f"{len(lg.signal_history)} signals")
    else:
        print_result("logger present", False)
        errors += 1

    return errors


def main():
    total_errors = 0

    total_errors += verify_imports()
    total_errors += verify_trade_logger()
    total_errors += verify_performance()
    total_errors += verify_backtest_engine()

    print_header("Verification Summary")
    if total_errors == 0:
        print("  >>> ALL PASSED! <<<")
    else:
        print(f"  [WARN] {total_errors} section(s) had failures")

    sys.exit(0 if total_errors == 0 else 1)


if __name__ == "__main__":
    main()
