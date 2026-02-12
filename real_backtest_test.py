#!/usr/bin/env python3
"""真实数据回测验证（使用Tushare）。"""

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from backtest.backtest_engine import BacktestEngine
from config.strategy_config import BACKTEST_CONFIG

# 使用真实数据（Tushare），基于优化后的配置
config = BACKTEST_CONFIG.copy()
config.update({
    "start_date": "2024-01-01",
    "end_date": "2025-12-31",
})

print("=== 真实数据回测测试 ===")
print(f"数据源: Tushare (从.env读取token)")
print(f"回测区间: {config['start_date']} ~ {config['end_date']}")
print(f"初始资金: {config['initial_capital']:,}")

engine = BacktestEngine(
    config=config,
    use_mock=False,  # 使用真实数据
    data_source="tushare"
)

result = engine.run(progress=True)

print("\n=== 回测结果 ===")
print(f"总收益率: {result['metrics']['total_return']:.2%}")
print(f"年化收益率: {result['metrics']['annual_return']:.2%}")
print(f"最大回撤: {result['metrics']['max_drawdown']:.2%}")
print(f"夏普比率: {result['metrics']['sharpe_ratio']:.3f}")
print(f"交易次数: {result['metrics']['total_trades']}")

# 验证因子计算是否正常
nav_series = result["nav_series"]
if len(nav_series) > 0:
    print(f"\n净值序列长度: {len(nav_series)}")
    print(f"起始净值: {nav_series.iloc[0]:.4f}")
    print(f"结束净值: {nav_series.iloc[-1]:.4f}")

# 检查信号数据
signals_df = result.get("signals_df")
if signals_df is not None and len(signals_df) > 0:
    print(f"\n信号数据行数: {len(signals_df)}")

    # 检查是否有非零的宏观评分
    if "macro_score" in signals_df.columns:
        non_zero_scores = (signals_df["macro_score"] != 0).sum()
        print(f"非零宏观评分天数: {non_zero_scores}/{len(signals_df)}")

        if non_zero_scores > 0:
            sample_scores = signals_df[signals_df["macro_score"] != 0]["macro_score"].head(5).tolist()
            print(f"样本评分: {sample_scores}")

print("\n✅ 回测验证完成")
