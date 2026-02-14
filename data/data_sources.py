"""Tushare Pro 数据源封装及Mock数据生成。

所有API调用集中在此模块，上层通过DataFetcher间接使用。
支持数据源: Tushare Pro(需token) / Mock
IOPV用基金收盘净值替代。
"""

from __future__ import annotations

import math
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
# Tushare Pro 配置
# ──────────────────────────────────────────────

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

TUSHARE_TOKEN: str = os.getenv("TUSHARE_TOKEN", "")


def _to_ts_code(code: str) -> str:
    """将6位ETF代码转换为Tushare ts_code格式。

    规则: 51xxxx/58xxxx → .SH (上交所), 15xxxx/16xxxx/56xxxx → .SZ (深交所)
    """
    code = str(code).zfill(6)
    if code.startswith(("51", "58", "56")):
        # 56开头可能是深交所也可能是上交所, 但562500等是SH
        if code.startswith("56"):
            return f"{code}.SH"
        return f"{code}.SH"
    return f"{code}.SZ"


def _to_index_ts_code(code: str) -> str:
    """将指数代码转换为Tushare ts_code格式。

    规则: 000xxx → .SH (上证), 399xxx → .SZ (深证)
    """
    code = str(code).zfill(6)
    if code.startswith("399"):
        return f"{code}.SZ"
    return f"{code}.SH"


def set_tushare_token(token: str):
    """设置Tushare Pro API Token。"""
    global TUSHARE_TOKEN
    TUSHARE_TOKEN = token


def probe_tushare() -> DataSourceStatus:
    """探测 Tushare Pro 可用性。"""
    try:
        import tushare as ts
        if not TUSHARE_TOKEN:
            return DataSourceStatus("tushare", False, "Tushare token未设置")
        pro = ts.pro_api(TUSHARE_TOKEN)
        # 简单探测: 获取1天交易日历
        df = pro.trade_cal(exchange='SSE', start_date='20250101', end_date='20250102')
        if df is not None and not df.empty:
            return DataSourceStatus("tushare", True, f"Tushare Pro 可用 (v{ts.__version__})")
        return DataSourceStatus("tushare", False, "Tushare Pro 返回空数据")
    except Exception as exc:
        return DataSourceStatus("tushare", False, f"Tushare Pro 不可用: {exc}")


# ──────────────────────────────────────────────
# ETF日线行情
# ──────────────────────────────────────────────

def fetch_etf_daily_tushare(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """通过 Tushare fund_daily 获取ETF日线行情。

    Returns:
        DataFrame with columns: date, code, open, high, low, close, volume, amount
    """
    import tushare as ts

    pro = ts.pro_api(TUSHARE_TOKEN)
    ts_code = _to_ts_code(code)
    sd = start_date.replace("-", "")
    ed = end_date.replace("-", "")

    try:
        df = pro.fund_daily(
            ts_code=ts_code,
            start_date=sd,
            end_date=ed,
            fields='ts_code,trade_date,open,high,low,close,vol,amount'
        )
    except Exception as exc:
        logger.warning(f"Tushare fund_daily 失败 ({ts_code}): {exc}")
        return pd.DataFrame()

    if df is None or df.empty:
        logger.warning(f"Tushare ETF日线数据为空: {ts_code}")
        return pd.DataFrame()

    result = pd.DataFrame({
        "date": pd.to_datetime(df["trade_date"]),
        "code": code,
        "open": pd.to_numeric(df["open"], errors="coerce"),
        "high": pd.to_numeric(df["high"], errors="coerce"),
        "low": pd.to_numeric(df["low"], errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
        "volume": pd.to_numeric(df["vol"], errors="coerce"),
        "amount": pd.to_numeric(df["amount"], errors="coerce"),
    })

    # Tushare: vol单位是手(100股), amount单位是千元 → 转换为股和元
    result["volume"] = result["volume"] * 100
    result["amount"] = result["amount"] * 1000

    result.sort_values("date", inplace=True)
    result.reset_index(drop=True, inplace=True)
    return result


# ──────────────────────────────────────────────
# ETF份额数据
# ──────────────────────────────────────────────

def fetch_etf_shares_tushare(
    codes: list,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """通过 Tushare etf_share_size 获取ETF份额数据。

    接口说明:
    - 单次最大5000条，可根据代码或日期循环提取
    - 需要8000积分

    Args:
        codes: ETF代码列表（6位代码）
        start_date: 开始日期 (YYYY-MM-DD 或 YYYYMMDD)
        end_date: 结束日期 (YYYY-MM-DD 或 YYYYMMDD)

    Returns:
        DataFrame with columns: date, code, share_total (万份)
    """
    import tushare as ts

    pro = ts.pro_api(TUSHARE_TOKEN)
    sd = start_date.replace("-", "")
    ed = end_date.replace("-", "")

    all_parts = []

    for code in codes:
        ts_code = _to_ts_code(code)
        try:
            df = pro.etf_share_size(
                ts_code=ts_code,
                start_date=sd,
                end_date=ed,
            )
        except Exception as exc:
            logger.warning(f"Tushare etf_share_size 失败 ({ts_code}): {exc}")
            continue

        if df is None or df.empty:
            continue

        # 字段映射: total_share (万份)
        part = pd.DataFrame({
            "date": pd.to_datetime(df["trade_date"]),
            "code": code,
            "share_total": pd.to_numeric(df["total_share"], errors="coerce"),
        })
        all_parts.append(part)
        logger.info(f"Tushare份额数据: {code} {len(part)}条")

    if not all_parts:
        return pd.DataFrame()

    result = pd.concat(all_parts, ignore_index=True)
    result.sort_values(["code", "date"], inplace=True)
    result.reset_index(drop=True, inplace=True)
    return result


# ──────────────────────────────────────────────
# 股票技术面因子（MACD、均线等）
# ──────────────────────────────────────────────

def fetch_stk_factor_pro_tushare(
    code: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """通过 Tushare stk_factor_pro 获取股票技术面因子数据。

    接口说明:
    - 包含MACD、均线、KDJ等技术指标
    - 需要5000积分以上权限
    - 单次最多返回10000条

    Args:
        code: ETF代码（6位）
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)

    Returns:
        DataFrame with columns: date, code, macd, macd_dea, macd_dif,
                               ma5, ma10, ma20, ma60, etc.
    """
    import tushare as ts

    pro = ts.pro_api(TUSHARE_TOKEN)
    ts_code = _to_ts_code(code)
    sd = start_date.replace("-", "")
    ed = end_date.replace("-", "")

    try:
        df = pro.stk_factor_pro(
            ts_code=ts_code,
            start_date=sd,
            end_date=ed,
        )
    except Exception as exc:
        logger.warning(f"Tushare stk_factor_pro 失败 ({ts_code}): {exc}")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    # 字段映射 - 选择我们需要的指标
    result_columns = {
        "date": pd.to_datetime(df["trade_date"]),
        "code": code,
        # MACD指标
        "macd": pd.to_numeric(df.get("macd_bfq", pd.NA), errors="coerce"),
        "macd_dea": pd.to_numeric(df.get("macd_dea_bfq", pd.NA), errors="coerce"),
        "macd_dif": pd.to_numeric(df.get("macd_dif_bfq", pd.NA), errors="coerce"),
        # 均线指标
        "ma5": pd.to_numeric(df.get("ma_bfq_5", pd.NA), errors="coerce"),
        "ma10": pd.to_numeric(df.get("ma_bfq_10", pd.NA), errors="coerce"),
        "ma20": pd.to_numeric(df.get("ma_bfq_20", pd.NA), errors="coerce"),
        "ma60": pd.to_numeric(df.get("ma_bfq_60", pd.NA), errors="coerce"),
        # 其他技术指标
        "rsi_6": pd.to_numeric(df.get("rsi_bfq_6", pd.NA), errors="coerce"),
        "rsi_12": pd.to_numeric(df.get("rsi_bfq_12", pd.NA), errors="coerce"),
        "kdj_k": pd.to_numeric(df.get("kdj_k_bfq", pd.NA), errors="coerce"),
        "kdj_d": pd.to_numeric(df.get("kdj_d_bfq", pd.NA), errors="coerce"),
        "kdj_j": pd.to_numeric(df.get("kdj_j_bfq", pd.NA), errors="coerce"),
        "vol_ratio": pd.to_numeric(df.get("volume_ratio", pd.NA), errors="coerce"),
    }

    result = pd.DataFrame(result_columns)
    result = result.dropna(subset=["date"])
    result.sort_values("date", inplace=True)
    result.reset_index(drop=True, inplace=True)
    return result


# ──────────────────────────────────────────────
# 基金净值（IOPV替代）
# ──────────────────────────────────────────────

def fetch_etf_nav_tushare(code: str) -> pd.DataFrame:
    """通过 Tushare fund_nav 获取ETF历史净值（作为IOPV替代）。

    Returns:
        DataFrame with columns: date, code, nav (单位净值)
    """
    import tushare as ts

    pro = ts.pro_api(TUSHARE_TOKEN)
    ts_code = _to_ts_code(code)

    try:
        # fund_nav 获取基金净值
        df = pro.fund_nav(ts_code=ts_code)
    except Exception as exc:
        logger.warning(f"Tushare fund_nav 失败 ({ts_code}): {exc}")
        return pd.DataFrame()

    if df is None or df.empty:
        logger.warning(f"Tushare ETF净值数据为空: {ts_code}")
        return pd.DataFrame()

    # 字段映射: ann_date 公告日期, unit_nav 单位净值
    result = pd.DataFrame({
        "date": pd.to_datetime(df["ann_date"]),
        "nav": pd.to_numeric(df.get("unit_nav", df.get("nav", pd.NA)), errors="coerce"),
        "code": code,
    })

    result = result.dropna(subset=["date", "nav"])
    result.sort_values("date", inplace=True)
    result.reset_index(drop=True, inplace=True)
    return result[["date", "code", "nav"]]


# ──────────────────────────────────────────────
# 交易日历
# ──────────────────────────────────────────────

def fetch_trading_calendar_tushare() -> pd.DataFrame:
    """通过 Tushare trade_cal 获取交易日历。

    Returns:
        DataFrame with column: trade_date (datetime)
    """
    import tushare as ts

    pro = ts.pro_api(TUSHARE_TOKEN)

    try:
        df = pro.trade_cal(exchange='SSE', start_date='20100101', end_date='20301231')
    except Exception as exc:
        logger.warning(f"Tushare 交易日历获取失败: {exc}")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    # 仅保留交易日 (is_open == 1)
    open_days = df[df["is_open"] == 1].copy()
    result = pd.DataFrame({"trade_date": pd.to_datetime(open_days["cal_date"])})
    result.sort_values("trade_date", inplace=True)
    result.reset_index(drop=True, inplace=True)
    return result


# ──────────────────────────────────────────────
# 指数日线数据（用于相对动量基准）
# ──────────────────────────────────────────────

def fetch_index_daily_tushare(
    code: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """通过 Tushare index_daily 获取指数日线行情。

    Returns:
        DataFrame with columns: date, code, close
    """
    import tushare as ts

    pro = ts.pro_api(TUSHARE_TOKEN)
    ts_code = _to_index_ts_code(code)
    sd = start_date.replace("-", "")
    ed = end_date.replace("-", "")

    try:
        df = pro.index_daily(ts_code=ts_code, start_date=sd, end_date=ed)
    except Exception as exc:
        logger.warning(f"Tushare index_daily 失败 ({ts_code}): {exc}")
        return pd.DataFrame()

    if df is None or df.empty:
        logger.warning(f"Tushare 指数数据为空: {ts_code}")
        return pd.DataFrame()

    result = pd.DataFrame({
        "date": pd.to_datetime(df["trade_date"]),
        "close": pd.to_numeric(df["close"], errors="coerce"),
        "code": code,
    })

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
