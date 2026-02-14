"""ETF轮动策略回测系统 - 主入口。"""

from __future__ import annotations

import sys
import io
import argparse
import os

# Windows GBK console fix
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from config.strategy_config import BACKTEST_CONFIG, SIGNAL_CONFIG, RISK_CONFIG
from backtest.backtest_engine import BacktestEngine

# 加载 .env 文件（如果存在）
load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(description="ETF轮动策略回测")
    parser.add_argument("--mock", action="store_true", help="使用Mock数据")
    parser.add_argument("--tushare-token", type=str, default=None,
                        help="Tushare Pro API Token (覆盖 .env 配置)")
    parser.add_argument("--start", type=str, default=None, help="开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="结束日期 (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=None, help="初始资金")
    parser.add_argument("--no-progress", action="store_true", help="关闭进度输出")
    return parser.parse_args()


def get_tushare_token(args_token: str | None) -> str | None:
    """获取 Tushare token，优先级：命令行 > 环境变量 > 交互输入"""
    if args_token:
        return args_token
    # 从环境变量读取（由 load_dotenv() 加载 .env 文件）
    token = os.getenv("TUSHARE_TOKEN")
    if token:
        return token
    # 交互式输入
    print("\n  未找到 Tushare Token，请输入（或按 Ctrl+C 退出）：")
    try:
        token = input("  Tushare Pro API Token: ").strip()
        if token:
            return token
    except KeyboardInterrupt:
        print("\n  已取消")
        sys.exit(1)
    return None


def main():
    args = parse_args()

    # 构建配置
    config = BACKTEST_CONFIG.copy()
    if args.start:
        config["start_date"] = args.start
    if args.end:
        config["end_date"] = args.end
    if args.capital:
        config["initial_capital"] = args.capital

    # 获取 token（优先命令行，其次 .env 文件）
    token = get_tushare_token(args.tushare_token)

    # 创建引擎并运行
    engine = BacktestEngine(
        config=config,
        signal_config=SIGNAL_CONFIG,
        risk_config=RISK_CONFIG,
        use_mock=args.mock,
        tushare_token=token,
    )

    result = engine.run(progress=not args.no_progress)

    # 导出CSV（图表和HTML报告已由引擎生成）
    if not result["trades_df"].empty:
        result["trades_df"].to_csv("output/trades.csv", index=False, encoding="utf-8-sig")

    if not result["nav_series"].empty:
        result["nav_series"].to_csv("output/nav.csv", header=True, encoding="utf-8-sig")

    if not result["signals_df"].empty:
        result["signals_df"].to_csv("output/signals.csv", index=False, encoding="utf-8-sig")

    if result.get("logger") is not None:
        rebalances_df = result["logger"].get_rebalances_df()
        if not rebalances_df.empty:
            rebalances_df.to_csv("output/rebalances.csv", index=False, encoding="utf-8-sig")

        positions_df = result["logger"].get_positions_df()
        if not positions_df.empty:
            positions_df.to_csv("output/positions_detail.csv", index=False, encoding="utf-8-sig")

    print("\n  全部输出已保存到 output/ 目录")
    if "report_outputs" in result and "html_report" in result["report_outputs"]:
        print(f"  HTML报告路径: {result['report_outputs']['html_report']}")

    return result


if __name__ == "__main__":
    import os
    os.makedirs("output", exist_ok=True)
    main()
