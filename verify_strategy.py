"""Phase 2 验证脚本: 策略信号层。

验证内容:
1. 所有模块导入正常
2. MacroSignal: 5因子评分 + sigmoid仓位映射
3. BroadBasedRotation: 4因子评分 + 排名 + 权重分配
4. SectorRotation: 5因子评分 + 过热过滤 + 权重分配
5. SignalGenerator: 三层信号整合 + 震荡市检测
6. RiskControl: 多层止损/止盈
7. PortfolioManager: 调仓指令生成 + 风控联动
"""

from __future__ import annotations

import sys
import io

# Windows GBK console fix
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
        ("MacroSignal", "strategy.macro_signal", "MacroSignal"),
        ("smooth_position", "strategy.macro_signal", "smooth_position"),
        ("adaptive_threshold", "strategy.macro_signal", "adaptive_threshold"),
        ("BroadBasedRotation", "strategy.broad_based_rotation", "BroadBasedRotation"),
        ("SectorRotation", "strategy.sector_rotation", "SectorRotation"),
        ("SignalGenerator", "strategy.signal_generator", "SignalGenerator"),
        ("RiskControl", "strategy.risk_control", "RiskControl"),
        ("StopSignal", "strategy.risk_control", "StopSignal"),
        ("PortfolioManager", "strategy.portfolio_manager", "PortfolioManager"),
    ]

    for name, mod, attr in modules:
        try:
            m = __import__(mod, fromlist=[attr])
            obj = getattr(m, attr)
            print_result(name, True, str(type(obj).__name__))
        except Exception as e:
            print_result(name, False, str(e))
            errors += 1

    return errors


def verify_macro_signal() -> int:
    print_header("2. MacroSignal (5-factor + sigmoid)")
    errors = 0

    from strategy.macro_signal import MacroSignal, smooth_position

    # Test sigmoid
    p0 = smooth_position(0)
    p_pos = smooth_position(45)
    p_neg = smooth_position(-45)
    print_result("sigmoid(0)=0.5", abs(p0 - 0.5) < 0.01, f"{p0:.4f}")
    print_result("sigmoid(45)>0.9", p_pos > 0.9, f"{p_pos:.4f}")
    print_result("sigmoid(-45)<0.1", p_neg < 0.1, f"{p_neg:.4f}")
    if not (abs(p0 - 0.5) < 0.01 and p_pos > 0.9 and p_neg < 0.1):
        errors += 1

    # Test with mock data
    engine = MacroSignal()
    mock_data = pd.DataFrame({
        "mfi_z": [1.5, 0.8, -0.3],
        "mfa_z": [0.5, 0.3, -0.1],
        "intraday_premium_proxy_z": [0.2, 0.1, -0.5],
        "premium_rate_z": [-0.3, 0.1, 0.8],
        "cmc_z": [1.0, 0.5, -0.2],
    })

    result = engine.calculate(mock_data)
    print_result("5-factor score computed", "score" in result, f"score={result['score']:.2f}")
    print_result("equity_ratio in [0,1]", 0 <= result["total_equity_ratio"] <= 1,
                 f"ratio={result['total_equity_ratio']:.4f}")
    print_result("regime classified", result["regime"] in ("bullish", "bearish", "neutral"),
                 result["regime"])
    print_result("all components present",
                 all(k in result for k in ["net_inflow_component", "accel_component",
                                            "premium_component", "momentum_component"]),
                 f"{len(result)} keys")

    # Empty input
    empty_result = engine.calculate(pd.DataFrame())
    print_result("empty input handled", empty_result["score"] == 0.0 and empty_result["total_equity_ratio"] == 0.30)

    return errors


def verify_broad_rotation() -> int:
    print_header("3. BroadBasedRotation (4-factor + weights)")
    errors = 0

    from strategy.broad_based_rotation import BroadBasedRotation

    engine = BroadBasedRotation()

    mock_data = pd.DataFrame({
        "code": ["510300", "510500", "512100", "512890", "515000"],
        "name": ["HS300", "ZZ500", "ZZ1000", "HongLi", "KeJi"],
        "style": ["big", "mid", "small", "value", "tech"],
        "mfi_z": [2.0, 1.5, -0.5, 0.3, 1.8],
        "mfa_z": [1.0, 0.5, -0.3, 0.1, 0.8],
        "pdi_z": [-0.5, 0.2, 1.0, -0.3, 0.5],
        "cmc_z": [1.5, 1.0, -0.8, 0.5, 1.2],
    })

    ranked = engine.rank(mock_data)
    print_result("rank output not empty", not ranked.empty, f"{len(ranked)} rows")
    print_result("has rank column", "rank" in ranked.columns)
    print_result("has signal column", "signal" in ranked.columns)
    print_result("rank 1 is highest score",
                 float(ranked.iloc[0]["score"]) >= float(ranked.iloc[1]["score"]))

    signals = ranked["signal"].unique().tolist()
    print_result("signals valid", all(s in ("main", "aux", "minor", "avoid") for s in signals),
                 str(signals))

    # Weights
    weights = engine.allocate_weights(ranked, 0.25)
    print_result("weights allocated", len(weights) > 0, f"{len(weights)} ETFs")
    total_w = sum(weights.values())
    print_result("total weight <= 0.25", total_w <= 0.26, f"total={total_w:.4f}")
    max_w = max(weights.values()) if weights else 0
    print_result("single weight <= 0.30", max_w <= 0.30, f"max={max_w:.4f}")

    if ranked.empty or len(weights) == 0:
        errors += 1

    return errors


def verify_sector_rotation() -> int:
    print_header("4. SectorRotation (5-factor + overheat)")
    errors = 0

    from strategy.sector_rotation import SectorRotation

    engine = SectorRotation()

    mock_data = pd.DataFrame({
        "code": ["512480", "159819", "512690", "512010", "512880"],
        "name": ["BanDao", "AI", "BaiJiu", "YiYao", "ZhengQuan"],
        "category": ["tech", "tech", "consume", "medical", "finance"],
        "sector_flow_strength_z": [2.0, 1.5, 0.3, -0.5, 1.0],
        "mfa_z": [1.0, 0.8, 0.1, -0.3, 0.5],
        "intraday_premium_proxy_z": [0.5, 0.3, -0.2, 0.1, 0.4],
        "ret_20d": [0.08, 0.12, 0.03, -0.02, 0.05],
        "valuation_pct_z": [-0.5, 0.8, -0.3, -1.0, 0.2],
        "ret_10d": [0.10, 0.20, 0.05, 0.02, 0.08],  # AI overheated
    })

    ranked = engine.rank(mock_data, benchmark_ret_20d=0.04)
    print_result("rank output", not ranked.empty, f"{len(ranked)} rows")
    print_result("has overheat column", "overheat" in ranked.columns)

    # Check overheat filter
    ai_row = ranked[ranked["code"] == "159819"]
    if not ai_row.empty:
        is_overheated = bool(ai_row.iloc[0]["overheat"])
        print_result("AI (ret_10d=20%) flagged overheat", is_overheated)
        if not is_overheated:
            errors += 1
    else:
        print_result("AI row found", False)
        errors += 1

    signals = ranked["signal"].unique().tolist()
    print_result("signals valid",
                 all(s in ("attack", "support", "watch", "avoid") for s in signals),
                 str(signals))

    # Weights
    weights = engine.allocate_weights(ranked, 0.25)
    print_result("weights allocated", len(weights) > 0, f"{len(weights)} sectors")

    return errors


def verify_risk_control() -> int:
    print_header("5. RiskControl (multi-layer stop-loss)")
    errors = 0

    from strategy.risk_control import RiskControl

    rc = RiskControl()
    rc.init_portfolio(500_000)

    # Register positions
    rc.register_position("510300", 4.0, 10000)
    rc.register_position("512480", 2.0, 5000)
    print_result("positions registered", len(rc.trackers) == 2)

    # No stops initially
    signals = rc.check_all(500_000, {"510300": 4.0, "512480": 2.0})
    print_result("no stops at start", len(signals) == 0, f"{len(signals)} signals")

    # Simulate single ETF trailing stop (8% drop from peak)
    rc.trackers["510300"].update_price(4.5)  # peak
    signals = rc.check_all(500_000, {"510300": 4.1, "512480": 2.0})
    trailing_triggered = any(s.code == "510300" and s.action == "trailing_stop" for s in signals)
    print_result("trailing stop (8.8% drop)", trailing_triggered,
                 f"drop from 4.5->4.1 = {(4.5-4.1)/4.5:.1%}")

    # Simulate hard stop (>10% from entry)
    signals = rc.check_all(500_000, {"510300": 3.5, "512480": 2.0})
    hard_triggered = any(s.code == "510300" and s.action == "hard_stop" for s in signals)
    print_result("hard stop (12.5% loss)", hard_triggered,
                 f"entry=4.0, now=3.5, loss={(4.0-3.5)/4.0:.1%}")

    # Portfolio drawdown
    rc2 = RiskControl()
    rc2.init_portfolio(500_000)
    rc2.register_position("TEST", 10.0, 1000)

    # 6% drawdown → warning
    signals = rc2.check_all(470_000, {"TEST": 10.0})
    warning = any(s.action == "portfolio_warning" for s in signals)
    print_result("portfolio warning at 6%", warning, f"drawdown={(500000-470000)/500000:.1%}")

    # 9% drawdown → reduce
    rc2.portfolio_peak_value = 500_000  # reset peak
    signals = rc2.check_all(455_000, {"TEST": 10.0})
    reduce = any(s.action == "portfolio_reduce" for s in signals)
    print_result("portfolio reduce at 9%", reduce, f"drawdown={(500000-455000)/500000:.1%}")

    # 13% drawdown → exit
    rc2.portfolio_peak_value = 500_000
    signals = rc2.check_all(435_000, {"TEST": 10.0})
    exit_sig = any(s.action == "portfolio_exit" for s in signals)
    print_result("portfolio exit at 13%", exit_sig, f"drawdown={(500000-435000)/500000:.1%}")

    # Profit lock
    rc3 = RiskControl()
    rc3.init_portfolio(500_000)
    rc3.register_position("WIN", 10.0, 1000)
    rc3.trackers["WIN"].update_price(12.0)  # peak: +20%
    signals = rc3.check_all(500_000, {"WIN": 10.8})  # now: +8%, dropped from +20%
    profit_lock = any(s.action == "profit_lock" for s in signals)
    print_result("profit lock triggered", profit_lock,
                 f"peak profit=20%, current=8%, drop=12%")

    if not (trailing_triggered and hard_triggered and warning and reduce and exit_sig and profit_lock):
        errors += 1

    return errors


def verify_portfolio_manager() -> int:
    print_header("6. PortfolioManager (rebalance + risk)")
    errors = 0

    from strategy.portfolio_manager import PortfolioManager

    pm = PortfolioManager(initial_capital=500_000)
    print_result("init", pm.total_value == 500_000, f"capital={pm.total_value}")

    # Rebalance to buy
    prices = {"510300": 4.0, "510500": 6.0, "512480": 2.0}
    target = {"510300": 0.30, "510500": 0.20, "512480": 0.15}
    trades = pm.rebalance(target, prices)
    print_result("trades generated", len(trades) > 0, f"{len(trades)} trades")
    print_result("all buys", all(t.direction == "buy" for t in trades))

    # Execute
    result = pm.apply_trades(trades)
    print_result("trades executed", result["trades_executed"] > 0,
                 f"{result['trades_executed']} executed, cost={result['total_cost']:.2f}")
    print_result("positions created", len(pm.positions) > 0, f"{len(pm.positions)} positions")
    print_result("cash reduced", pm.cash < 500_000, f"cash={pm.cash:.0f}")

    # Check risk
    risk_signals = pm.check_risk(prices)
    print_result("no risk signals at start", len(risk_signals) == 0)

    # Summary
    summary = pm.portfolio_summary
    print_result("summary valid", summary["total_value"] > 0 and summary["positions"] > 0,
                 f"value={summary['total_value']:.0f}, positions={summary['positions']}")

    return errors


def verify_signal_generator() -> int:
    print_header("7. SignalGenerator (integration)")
    errors = 0

    from strategy.signal_generator import SignalGenerator
    from data.data_sources import generate_mock_etf_data
    from data.data_processor import DataProcessor

    sg = SignalGenerator()
    print_result("SignalGenerator created", True)

    # Generate mock data for a few ETFs
    processor = DataProcessor()
    market_data = {}
    test_codes = ["510300", "510500", "512480"]

    for code in test_codes:
        mock = generate_mock_etf_data(code, "20240101", "20240401")
        processed = processor.process(mock)
        market_data[code] = processed

    print_result("mock data prepared", len(market_data) == 3,
                 f"{len(market_data)} ETFs, {len(market_data['510300'])} days each")

    # Generate signals
    test_date = pd.Timestamp("2024-03-15")
    signals = sg.generate_signals(test_date, market_data)

    print_result("signals generated", "macro" in signals and "broad_ranked" in signals)
    print_result("macro score present", "score" in signals["macro"],
                 f"score={signals['macro']['score']:.2f}")
    print_result("equity ratio present", "total_equity_ratio" in signals,
                 f"ratio={signals['total_equity_ratio']:.4f}")
    print_result("target weights present", "target_weights" in signals,
                 f"{len(signals['target_weights'])} targets")
    print_result("choppy_mode present", "choppy_mode" in signals,
                 f"choppy={signals['choppy_mode']}")

    if "macro" not in signals:
        errors += 1

    return errors


def main():
    total_errors = 0

    total_errors += verify_imports()
    total_errors += verify_macro_signal()
    total_errors += verify_broad_rotation()
    total_errors += verify_sector_rotation()
    total_errors += verify_risk_control()
    total_errors += verify_portfolio_manager()
    total_errors += verify_signal_generator()

    print_header("Verification Summary")
    if total_errors == 0:
        print("  >>> ALL PASSED! <<<")
    else:
        print(f"  [WARN] {total_errors} section(s) had failures")

    sys.exit(0 if total_errors == 0 else 1)


if __name__ == "__main__":
    main()
