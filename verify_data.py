#!/usr/bin/env python3
"""数据模块验证脚本。

验证项目:
1. AKShare连通性（6个接口）
2. ETF日线数据获取
3. ETF份额数据获取
4. 基金净值数据获取
5. 交易日历
6. 指数数据
7. DataProcessor指标计算完整性
8. 缓存读写

用法：
    cd e:\\samba_workplace\\ETF
    python verify_data.py
"""

from __future__ import annotations

import sys
import os
import io
import traceback

# Windows控制台UTF-8编码处理
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# 确保项目根目录在path中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd


def print_header(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(name: str, passed: bool, detail: str = "") -> None:
    icon = "[PASS]" if passed else "[FAIL]"
    print(f"  {icon} {name}: {detail}")


def verify_config() -> int:
    """验证配置模块。"""
    print_header("1. 配置模块验证")
    errors = 0

    try:
        from config.etf_pool import (
            BROAD_BASED_ETF_POOL, SECTOR_ETF_POOL,
            get_all_etf_codes, get_broad_codes, get_sector_codes,
        )

        # 检查宽基池数量
        broad_count = len(BROAD_BASED_ETF_POOL)
        print_result("宽基池", broad_count == 10, f"{broad_count}只")

        # 检查行业池数量
        sector_count = len(SECTOR_ETF_POOL)
        print_result("行业池", sector_count == 20, f"{sector_count}只")

        # 检查无重叠
        broad_codes = set(get_broad_codes())
        sector_codes = set(get_sector_codes())
        overlap = broad_codes & sector_codes
        print_result("池子无重叠", len(overlap) == 0,
                     f"无重叠" if not overlap else f"重叠: {overlap}")
        if overlap:
            errors += 1

        # 检查总数
        all_codes = get_all_etf_codes()
        print_result("总ETF数量", len(all_codes) == 30, f"{len(all_codes)}只")

    except Exception as e:
        print_result("配置导入", False, str(e))
        errors += 1

    try:
        from config.strategy_config import BACKTEST_CONFIG, SIGNAL_CONFIG, RISK_CONFIG

        # 检查v2.0配置
        cap = BACKTEST_CONFIG["initial_capital"]
        print_result("初始资金", cap <= 1_000_000, f"{cap:,}元")

        freq = BACKTEST_CONFIG.get("rebalance_freq", {})
        is_layered = isinstance(freq, dict) and "macro" in freq
        print_result("分层调仓配置", is_layered, str(freq) if is_layered else "缺失")

        # 检查权重
        macro_w = SIGNAL_CONFIG["macro_weights"]
        has_accel = "flow_acceleration" in macro_w
        print_result("宏观层含资金流加速度", has_accel,
                     f'权重={macro_w.get("flow_acceleration", "缺失")}')

        # 检查止损
        has_trailing = "single_trailing_stop" in RISK_CONFIG
        print_result("多层止损配置", has_trailing,
                     f'追踪止损={RISK_CONFIG.get("single_trailing_stop", "缺失")}')

    except Exception as e:
        print_result("策略配置导入", False, str(e))
        errors += 1

    return errors


def verify_data_sources() -> int:
    """验证AKShare数据源连通性。"""
    print_header("2. AKShare数据源连通性")
    errors = 0

    from data.data_fetcher import DataFetcher

    fetcher = DataFetcher(fallback_to_mock=False, api_delay=1.0)
    results = fetcher.diagnose()

    for key, msg in results.items():
        passed = msg.startswith("[PASS]") or "PASS" in msg
        print_result(key, passed, msg)
        if not passed:
            errors += 1

    return errors


def verify_data_fetcher_mock() -> int:
    """验证DataFetcher的Mock模式（不依赖网络）。"""
    print_header("3. DataFetcher Mock模式")
    errors = 0

    from data.data_fetcher import DataFetcher

    # 强制使用mock
    fetcher = DataFetcher(data_source="disabled", fallback_to_mock=True, api_delay=0)

    # 测试单只ETF
    result = fetcher.fetch_etf_daily("510300", "2024-01-01", "2024-03-31")
    has_data = not result.data.empty and len(result.data) > 0
    print_result("Mock日线数据", has_data,
                 f'{result.source}, {len(result.data)}条' if has_data else '空')
    if not has_data:
        errors += 1

    # 检查字段完整性
    if has_data:
        expected_cols = {"date", "code", "open", "high", "low", "close", "volume", "amount"}
        actual_cols = set(result.data.columns)
        missing = expected_cols - actual_cols
        print_result("行情字段完整", not missing,
                     f"包含全部{len(expected_cols)}个字段" if not missing else f"缺失: {missing}")
        if missing:
            errors += 1

    return errors


def verify_data_processor() -> int:
    """验证DataProcessor指标计算。"""
    print_header("4. DataProcessor指标计算")
    errors = 0

    from data.data_sources import generate_mock_etf_data
    from data.data_processor import DataProcessor, standardize

    # 用mock数据生成测试集
    mock = generate_mock_etf_data("510300", "2023-01-01", "2024-12-31")
    print_result("Mock数据生成", not mock.empty, f"{len(mock)}条记录")

    # 全流程处理
    try:
        processed = DataProcessor.process(mock)
        print_result("全流程处理", not processed.empty, f"{len(processed)}条, {len(processed.columns)}列")
    except Exception as e:
        print_result("全流程处理", False, str(e))
        traceback.print_exc()
        return errors + 1

    # 检查新增指标列
    v2_columns = [
        "ret_1d", "ret_5d", "ret_10d", "ret_20d", "vol_20d",    # 收益率
        "cmc",                                                     # 多周期动量
        "net_inflow", "mfi", "mfa",                               # 资金流
        "sector_flow_strength",                                    # 行业资金流
        "pdi",                                                     # 折溢价指数
        "intraday_premium_proxy",                                  # 盘中溢价代理
        "valuation_pct",                                           # 估值分位
        "mfi_z", "mfa_z", "pdi_z", "cmc_z",                      # 标准化列
    ]

    present = []
    missing = []
    for col in v2_columns:
        if col in processed.columns:
            present.append(col)
        else:
            missing.append(col)

    print_result(f"v2.0指标列 ({len(present)}/{len(v2_columns)})",
                 len(missing) == 0,
                 f"全部存在" if not missing else f"缺失: {missing}")
    if missing:
        errors += 1

    # 检查非全NA
    all_na_cols = []
    for col in present:
        if processed[col].isna().all():
            all_na_cols.append(col)

    # 前面几行NA是正常的（rolling需要warmup），检查后半段
    half = len(processed) // 2
    late_na_cols = []
    for col in present:
        if processed[col].iloc[half:].isna().all():
            late_na_cols.append(col)

    print_result("指标后半段有值",
                 len(late_na_cols) == 0,
                 f"全部有值" if not late_na_cols else f"仍全NA: {late_na_cols}")
    if late_na_cols:
        errors += 1

    # 验证standardize函数
    test_series = pd.Series(np.random.randn(200))
    z = standardize(test_series, window=60)
    z_valid = z.dropna()
    in_range = (z_valid >= -3).all() and (z_valid <= 3).all()
    print_result("standardize函数", in_range and len(z_valid) > 0,
                 f"范围[{z_valid.min():.2f}, {z_valid.max():.2f}], 有效{len(z_valid)}条")
    if not in_range:
        errors += 1

    # 验证MFA（资金流加速度）有正有负
    if "mfa" in processed.columns:
        mfa_valid = processed["mfa"].dropna()
        has_pos = (mfa_valid > 0).any()
        has_neg = (mfa_valid < 0).any()
        print_result("MFA有正有负", has_pos and has_neg,
                     f"正值{(mfa_valid>0).sum()}条, 负值{(mfa_valid<0).sum()}条")

    return errors


def verify_cache() -> int:
    """验证缓存管理器。"""
    print_header("5. 缓存管理器")
    errors = 0

    from data.cache_manager import CacheManager

    cache = CacheManager()

    # 写入测试
    test_df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=5),
        "code": "TEST",
        "value": [1, 2, 3, 4, 5],
    })
    cache.write("test", "test_key", test_df)

    # 读取测试
    read_back = cache.read("test", "test_key")
    print_result("缓存写入/读取", read_back is not None and len(read_back) == 5,
                 f"写入5条, 读回{len(read_back) if read_back is not None else 0}条")
    if read_back is None or len(read_back) != 5:
        errors += 1

    # 增量追加测试
    append_df = pd.DataFrame({
        "date": pd.date_range("2024-01-04", periods=3),
        "code": "TEST",
        "value": [40, 50, 60],
    })
    merged = cache.append("test", "test_key", append_df)
    print_result("增量追加去重", len(merged) == 6,
                 f"合并后{len(merged)}条 (期望6条: 5原始+3追加-2重复)")
    if len(merged) != 6:
        errors += 1

    # 清理测试缓存
    cache.clear("test")
    print_result("缓存清理", cache.read("test", "test_key") is None, "清理成功")

    return errors


def main() -> None:
    """运行全部验证。"""
    print("\n" + "=" * 60)
    print("  ETF轮动策略 - 数据模块验证 (Phase 1)")
    print("=" * 60)

    total_errors = 0

    # 1. 配置验证（不依赖网络）
    total_errors += verify_config()

    # 2. AKShare连通性（需要网络）
    print("\n  [提示] 正在测试AKShare连通性，可能需要10-20秒...")
    try:
        total_errors += verify_data_sources()
    except Exception as e:
        print(f"\n  [WARN] AKShare连通性测试异常: {e}")
        print("  跳过在线测试，继续离线验证...")

    # 3. Mock模式（不依赖网络）
    total_errors += verify_data_fetcher_mock()

    # 4. 指标计算（不依赖网络）
    total_errors += verify_data_processor()

    # 5. 缓存（不依赖网络）
    total_errors += verify_cache()

    # 汇总
    print_header("验证汇总")
    if total_errors == 0:
        print("  >>> ALL PASSED! <<<")
    else:
        print(f"  [WARN] {total_errors} 项未通过，请检查上方详情")

    sys.exit(0 if total_errors == 0 else 1)


if __name__ == "__main__":
    main()
