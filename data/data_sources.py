"""AKShare数据源封装及Mock数据生成。

所有AKShare API调用集中在此模块，上层通过DataFetcher间接使用。
数据源策略: AKShare为唯一数据源，IOPV用基金收盘净值替代。
"""

from __future__ import annotations

import math
import time
import logging
from dataclasses import dataclass
from typing import Optional, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DataSourceStatus:
    name: str
    available: bool
    message: str


# ──────────────────────────────────────────────
# AKShare 探测
# ──────────────────────────────────────────────

def probe_akshare() -> DataSourceStatus:
    """探测 akshare 可用性。"""
    try:
        import akshare as ak  # type: ignore
        _ = ak.__version__
        return DataSourceStatus("akshare", True, f"akshare {ak.__version__} 可用")
    except Exception as exc:
        return DataSourceStatus("akshare", False, f"akshare 不可用: {exc}")


# ──────────────────────────────────────────────
# ETF日线行情
# ──────────────────────────────────────────────

def fetch_etf_daily_akshare(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """通过 fund_etf_hist_em 获取ETF日线行情（OHLCV + 成交额）。

    Returns:
        DataFrame with columns: date, code, open, high, low, close, volume, amount
    """
    import akshare as ak  # type: ignore

    df = ak.fund_etf_hist_em(
        symbol=code,
        period="daily",
        start_date=start_date.replace("-", ""),
        end_date=end_date.replace("-", ""),
        adjust="",
    )
    if df is None or df.empty:
        logger.warning(f"ETF日线数据为空: {code}")
        return pd.DataFrame()

    rename_map = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
    }
    mapped = df.rename(columns=rename_map)
    required = ["date", "open", "high", "low", "close", "volume", "amount"]
    for col in required:
        if col not in mapped.columns:
            mapped[col] = pd.NA

    mapped = mapped[required].copy()
    mapped["date"] = pd.to_datetime(mapped["date"])
    mapped["code"] = code

    for col in ["open", "high", "low", "close", "volume", "amount"]:
        mapped[col] = pd.to_numeric(mapped[col], errors="coerce")

    mapped.sort_values("date", inplace=True)
    mapped.reset_index(drop=True, inplace=True)
    return mapped


# ──────────────────────────────────────────────
# ETF份额数据
# ──────────────────────────────────────────────

def fetch_etf_shares_akshare(date: str) -> pd.DataFrame:
    """获取指定日期的全市场ETF份额。

    实现方式:
    - 上交所ETF (51xxxx/58xxxx): fund_etf_scale_sse(date) 支持历史日期
    - 深交所ETF (15xxxx/56xxxx): fund_etf_scale_szse() 仅快照，无日期参数

    Args:
        date: 日期字符串, 格式 YYYYMMDD 或 YYYY-MM-DD

    Returns:
        DataFrame with columns: date, code, share_total
    """
    import akshare as ak  # type: ignore

    date_str = date.replace("-", "")
    all_parts = []

    # 1. 上交所ETF份额（支持历史查询）
    try:
        sse_df = ak.fund_etf_scale_sse(date=date_str)
        if sse_df is not None and not sse_df.empty:
            # 列名容错: 可能是 "基金代码"/"代码", "份额"/"基金份额"
            rename_map = {}
            for col in sse_df.columns:
                col_lower = str(col)
                if "代码" in col_lower:
                    rename_map[col] = "code"
                elif "份额" in col_lower:
                    rename_map[col] = "share_total"
                elif "日期" in col_lower:
                    rename_map[col] = "raw_date"
            sse_df.rename(columns=rename_map, inplace=True)

            if "code" in sse_df.columns and "share_total" in sse_df.columns:
                part = sse_df[["code", "share_total"]].copy()
                part["code"] = part["code"].astype(str).str.zfill(6)
                part["share_total"] = pd.to_numeric(part["share_total"], errors="coerce")
                part["date"] = pd.to_datetime(date_str)
                all_parts.append(part)
                logger.info(f"SSE ETF份额: {len(part)}条 ({date_str})")
    except Exception as exc:
        logger.warning(f"SSE ETF份额获取失败 ({date_str}): {exc}")

    # 2. 深交所ETF份额（仅快照，无日期参数）
    try:
        szse_df = ak.fund_etf_scale_szse()
        if szse_df is not None and not szse_df.empty:
            rename_map = {}
            for col in szse_df.columns:
                col_lower = str(col)
                if "代码" in col_lower:
                    rename_map[col] = "code"
                elif "份额" in col_lower:
                    rename_map[col] = "share_total"
            szse_df.rename(columns=rename_map, inplace=True)

            if "code" in szse_df.columns and "share_total" in szse_df.columns:
                part = szse_df[["code", "share_total"]].copy()
                part["code"] = part["code"].astype(str).str.zfill(6)
                part["share_total"] = pd.to_numeric(part["share_total"], errors="coerce")
                part["date"] = pd.to_datetime(date_str)
                all_parts.append(part)
                logger.info(f"SZSE ETF份额: {len(part)}条")
    except Exception as exc:
        logger.warning(f"SZSE ETF份额获取失败: {exc}")

    if not all_parts:
        logger.warning(f"ETF份额数据为空: {date_str}")
        return pd.DataFrame()

    result = pd.concat(all_parts, ignore_index=True)
    result.drop_duplicates(subset=["code"], keep="last", inplace=True)
    return result[["date", "code", "share_total"]]


# ──────────────────────────────────────────────
# 基金净值（IOPV替代）
# ──────────────────────────────────────────────

def fetch_etf_nav_akshare(code: str) -> pd.DataFrame:
    """通过 fund_etf_fund_info_em 获取ETF历史净值（作为IOPV替代）。

    Returns:
        DataFrame with columns: date, code, nav (单位净值)
    """
    import akshare as ak  # type: ignore

    try:
        df = ak.fund_etf_fund_info_em(fund=code, start_date="20200101")
    except Exception as exc:
        logger.warning(f"ETF净值数据获取失败 ({code}): {exc}")
        return pd.DataFrame()

    if df is None or df.empty:
        logger.warning(f"ETF净值数据为空: {code}")
        return pd.DataFrame()

    # 字段名容错
    rename_candidates = {
        "净值日期": "date",
        "单位净值": "nav",
    }
    for src, dst in rename_candidates.items():
        if src in df.columns:
            df.rename(columns={src: dst}, inplace=True)

    if "date" not in df.columns or "nav" not in df.columns:
        logger.warning(f"ETF净值数据字段不完整: {list(df.columns)}")
        return pd.DataFrame()

    result = df[["date", "nav"]].copy()
    result["date"] = pd.to_datetime(result["date"])
    result["nav"] = pd.to_numeric(result["nav"], errors="coerce")
    result["code"] = code

    result.sort_values("date", inplace=True)
    result.reset_index(drop=True, inplace=True)
    return result[["date", "code", "nav"]]


# ──────────────────────────────────────────────
# 交易日历
# ──────────────────────────────────────────────

def fetch_trading_calendar_akshare() -> pd.DataFrame:
    """获取A股交易日历。

    Returns:
        DataFrame with column: trade_date (datetime)
    """
    import akshare as ak  # type: ignore

    try:
        df = ak.tool_trade_date_hist_sina()
    except Exception as exc:
        logger.warning(f"交易日历获取失败: {exc}")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    # 字段名处理
    if "trade_date" in df.columns:
        col = "trade_date"
    else:
        col = df.columns[0]

    result = pd.DataFrame({"trade_date": pd.to_datetime(df[col])})
    result.sort_values("trade_date", inplace=True)
    result.reset_index(drop=True, inplace=True)
    return result


# ──────────────────────────────────────────────
# 指数日线数据（用于相对动量基准）
# ──────────────────────────────────────────────

def fetch_index_daily_akshare(
    code: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """获取指数日线行情，用于计算相对动量。

    Args:
        code: 指数代码, 如 "000300" (沪深300)

    Returns:
        DataFrame with columns: date, code, close
    """
    import akshare as ak  # type: ignore

    max_retries = 3
    for attempt in range(max_retries):
        try:
            df = ak.index_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
            )
            break
        except Exception as exc:
            if attempt < max_retries - 1:
                logger.info(f"指数数据获取重试 ({code}), 第{attempt+2}次...")
                time.sleep(2)
            else:
                logger.warning(f"指数数据获取失败 ({code}): {exc}")
                return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    rename_map = {"日期": "date", "收盘": "close"}
    mapped = df.rename(columns=rename_map)

    if "date" not in mapped.columns or "close" not in mapped.columns:
        logger.warning(f"指数数据字段不完整: {list(mapped.columns)}")
        return pd.DataFrame()

    result = mapped[["date", "close"]].copy()
    result["date"] = pd.to_datetime(result["date"])
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result["code"] = code

    result.sort_values("date", inplace=True)
    result.reset_index(drop=True, inplace=True)
    return result


# ──────────────────────────────────────────────
# Mock数据生成
# ──────────────────────────────────────────────

def generate_mock_etf_data(
    code: str,
    start_date: str,
    end_date: str,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """生成用于开发调试的模拟ETF行情与衍生字段。"""
    trading_days = pd.bdate_range(start=start_date, end=end_date)
    if len(trading_days) == 0:
        return pd.DataFrame()

    rng_seed = seed if seed is not None else (
        sum(ord(c) for c in code) + len(trading_days)
    )
    rng = np.random.default_rng(rng_seed)

    base_price = 0.8 + (int(code[-2:]) % 30) / 10.0
    daily_ret = rng.normal(loc=0.0005, scale=0.018, size=len(trading_days))
    trend = np.sin(np.linspace(0, math.pi * 6, len(trading_days))) * 0.002
    returns = daily_ret + trend

    close = [base_price]
    for r in returns[1:]:
        close.append(max(0.2, close[-1] * (1.0 + r)))
    close_s = pd.Series(close, index=trading_days)

    high_s = close_s * (1 + np.abs(rng.normal(0.003, 0.004, len(trading_days))))
    low_s = close_s * (1 - np.abs(rng.normal(0.003, 0.004, len(trading_days))))
    open_s = (high_s + low_s) / 2 + rng.normal(0.0, 0.01, len(trading_days))

    volume_s = rng.integers(2_000_000, 30_000_000, size=len(trading_days))
    amount_s = close_s.values * volume_s

    share_changes = rng.normal(0, 1_200_000, len(trading_days))
    share_total = np.cumsum(share_changes) + rng.integers(1_000_000_000, 5_000_000_000)
    share_total = np.clip(share_total, 100_000_000, None)

    nav_s = close_s * (1 - rng.normal(0, 0.0015, len(trading_days)))
    premium_rate = (close_s - nav_s) / nav_s * 100

    return pd.DataFrame({
        "date": trading_days,
        "code": code,
        "open": open_s.values,
        "high": high_s.values,
        "low": low_s.values,
        "close": close_s.values,
        "volume": volume_s,
        "amount": amount_s,
        "share_total": share_total,
        "nav": nav_s.values,
        "premium_rate": premium_rate.values,
    })
