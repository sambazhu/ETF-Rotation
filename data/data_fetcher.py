"""统一数据获取入口。

职责：
1. 协调 AKShare / Tushare Pro API调用与本地缓存
2. 合并行情、份额、净值为完整数据集
3. 提供带进度显示的批量获取
4. 数据源可用性诊断
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from config.strategy_config import BACKTEST_CONFIG
from config.etf_pool import get_all_etf_codes, get_broad_codes, get_sector_codes, BENCHMARK_INDICES
from data.cache_manager import CacheManager
from data.data_sources import (
    DataSourceStatus,
    probe_akshare,
    fetch_etf_daily_akshare,
    fetch_etf_shares_akshare,
    fetch_etf_nav_akshare,
    fetch_trading_calendar_akshare,
    fetch_index_daily_akshare,
    generate_mock_etf_data,
    # Tushare Pro
    set_tushare_token,
    probe_tushare,
    fetch_etf_daily_tushare,
    fetch_index_daily_tushare,
    fetch_trading_calendar_tushare,
)

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    data: pd.DataFrame
    source: str
    message: str


class DataFetcher:
    """统一数据获取入口，优先缓存 → Tushare/AKShare → Mock回退。"""

    def __init__(
        self,
        data_source: str = "akshare",
        fallback_to_mock: bool = True,
        cache_dir: Optional[str] = None,
        api_delay: float = 0.5,
        tushare_token: Optional[str] = None,
    ):
        self.source = data_source
        self.fallback_to_mock = fallback_to_mock
        self.cache = CacheManager(cache_dir)
        self.api_delay = api_delay  # API调用间隔（秒），防止被限频

        # Tushare token 初始化
        if tushare_token:
            set_tushare_token(tushare_token)

        self.source_status = self._probe_source()

    def _probe_source(self) -> DataSourceStatus:
        if self.source == "tushare":
            return probe_tushare()
        if self.source == "akshare":
            return probe_akshare()
        return DataSourceStatus(self.source, False, f"暂不支持: {self.source}")

    def _api_sleep(self) -> None:
        """API调用间隔，防止频率限制。"""
        if self.api_delay > 0:
            time.sleep(self.api_delay)

    # ──────────────────────────────────────────
    # ETF日线行情
    # ──────────────────────────────────────────

    def fetch_etf_daily(
        self, code: str, start_date: str, end_date: str, use_cache: bool = True
    ) -> FetchResult:
        """获取单个ETF日线数据，优先读缓存。"""
        if use_cache:
            cached = self.cache.read("etf_daily", code)
            if cached is not None and not cached.empty:
                # 筛选日期范围
                cached["date"] = pd.to_datetime(cached["date"])
                mask = (cached["date"] >= start_date) & (cached["date"] <= end_date)
                filtered = cached[mask].copy()
                if not filtered.empty:
                    return FetchResult(filtered, "cache", f"缓存命中 {len(filtered)}条")

        if self.source_status.available:
            try:
                if self.source == "tushare":
                    df = fetch_etf_daily_tushare(code, start_date, end_date)
                else:
                    df = fetch_etf_daily_akshare(code, start_date, end_date)
                if not df.empty:
                    self.cache.append("etf_daily", code, df)
                    self._api_sleep()
                    return FetchResult(df, self.source, f"真实数据 {len(df)}条")
            except Exception as exc:
                logger.warning(f"{self.source}获取失败 ({code}): {exc}")
                if not self.fallback_to_mock:
                    raise

        if self.fallback_to_mock:
            mock = generate_mock_etf_data(code, start_date, end_date)
            return FetchResult(mock, "mock", "模拟数据")

        raise RuntimeError(f"数据源不可用且未启用mock: {code}")

    # ──────────────────────────────────────────
    # ETF份额数据
    # ──────────────────────────────────────────

    def fetch_etf_shares(self, date: str) -> FetchResult:
        """获取指定日期的全市场ETF份额。"""
        date_key = pd.to_datetime(date).strftime("%Y%m%d")

        cached = self.cache.read("shares", date_key)
        if cached is not None and not cached.empty:
            return FetchResult(cached, "cache", f"份额缓存命中 {len(cached)}条")

        if self.source_status.available:
            try:
                df = fetch_etf_shares_akshare(date_key)
                if not df.empty:
                    self.cache.write("shares", date_key, df)
                    self._api_sleep()
                    return FetchResult(df, "akshare", f"份额数据 {len(df)}条")
            except Exception as exc:
                logger.warning(f"份额数据获取失败 ({date_key}): {exc}")

        return FetchResult(pd.DataFrame(), "none", "份额数据不可用")

    # ──────────────────────────────────────────
    # 基金净值（IOPV替代）
    # ──────────────────────────────────────────

    def fetch_etf_nav(self, code: str, use_cache: bool = True) -> FetchResult:
        """获取ETF历史净值序列。"""
        if use_cache:
            cached = self.cache.read("nav", code)
            if cached is not None and not cached.empty:
                return FetchResult(cached, "cache", f"净值缓存命中 {len(cached)}条")

        if self.source_status.available:
            try:
                df = fetch_etf_nav_akshare(code)
                if not df.empty:
                    self.cache.write("nav", code, df)
                    self._api_sleep()
                    return FetchResult(df, "akshare", f"净值数据 {len(df)}条")
            except Exception as exc:
                logger.warning(f"净值数据获取失败 ({code}): {exc}")

        return FetchResult(pd.DataFrame(), "none", "净值数据不可用")

    # ──────────────────────────────────────────
    # 指数日线
    # ──────────────────────────────────────────

    def fetch_index(
        self, code: str, start_date: str, end_date: str, use_cache: bool = True
    ) -> FetchResult:
        """获取指数日线行情。"""
        cache_key = f"index_{code}"
        if use_cache:
            cached = self.cache.read("index", code)
            if cached is not None and not cached.empty:
                cached["date"] = pd.to_datetime(cached["date"])
                mask = (cached["date"] >= start_date) & (cached["date"] <= end_date)
                filtered = cached[mask].copy()
                if not filtered.empty:
                    return FetchResult(filtered, "cache", f"指数缓存命中 {len(filtered)}条")

        if self.source_status.available:
            try:
                if self.source == "tushare":
                    df = fetch_index_daily_tushare(code, start_date, end_date)
                else:
                    df = fetch_index_daily_akshare(code, start_date, end_date)
                if not df.empty:
                    self.cache.append("index", code, df)
                    self._api_sleep()
                    return FetchResult(df, self.source, f"指数数据 {len(df)}条")
            except Exception as exc:
                logger.warning(f"指数数据获取失败 ({code}): {exc}")

        return FetchResult(pd.DataFrame(), "none", "指数数据不可用")

    # ──────────────────────────────────────────
    # 交易日历
    # ──────────────────────────────────────────

    def fetch_trading_calendar(self) -> FetchResult:
        """获取交易日历。"""
        cached = self.cache.read("calendar", "trade_dates")
        if cached is not None and not cached.empty:
            return FetchResult(cached, "cache", f"日历缓存命中 {len(cached)}条")

        if self.source_status.available:
            try:
                if self.source == "tushare":
                    df = fetch_trading_calendar_tushare()
                else:
                    df = fetch_trading_calendar_akshare()
                if not df.empty:
                    self.cache.write("calendar", "trade_dates", df)
                    return FetchResult(df, self.source, f"交易日历 {len(df)}条")
            except Exception as exc:
                logger.warning(f"交易日历获取失败: {exc}")

        return FetchResult(pd.DataFrame(), "none", "交易日历不可用")

    # ──────────────────────────────────────────
    # 批量获取（带进度）
    # ──────────────────────────────────────────

    def fetch_all_etf_data(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        codes: Optional[List[str]] = None,
        include_nav: bool = True,
    ) -> Dict[str, pd.DataFrame]:
        """批量获取所有ETF的完整数据（行情+净值合并），带进度显示。

        Returns:
            Dict[code, DataFrame]: 每个ETF的合并数据
        """
        start = start_date or BACKTEST_CONFIG["start_date"]
        end = end_date or BACKTEST_CONFIG["end_date"]
        target_codes = codes or get_all_etf_codes()
        total = len(target_codes)

        result: Dict[str, pd.DataFrame] = {}
        for i, code in enumerate(target_codes, 1):
            print(f"  [{i}/{total}] {code} ...", end=" ", flush=True)

            # 1. 日线行情
            daily_result = self.fetch_etf_daily(code, start, end)
            df = daily_result.data.copy()

            # 2. 净值数据（合并到日线中作为IOPV替代）
            if include_nav and not df.empty:
                nav_result = self.fetch_etf_nav(code)
                if not nav_result.data.empty:
                    nav_df = nav_result.data[["date", "nav"]].copy()
                    nav_df["date"] = pd.to_datetime(nav_df["date"])
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.merge(nav_df, on="date", how="left")
                    df["nav"] = df["nav"].ffill().bfill()
                else:
                    df["nav"] = df["close"]  # 回退: 用收盘价
            elif not df.empty:
                df["nav"] = df["close"]

            # 3. 计算溢价率
            if not df.empty and "nav" in df.columns:
                df["premium_rate"] = (df["close"] - df["nav"]) / df["nav"] * 100

            result[code] = df
            status = daily_result.source
            print(f"✓ ({status}, {len(df)}条)")

        print(f"\n完成! 共获取 {len(result)} 只ETF数据")
        return result

    def fetch_shares_for_period(
        self,
        start_date: str,
        end_date: str,
        codes: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """获取一段时间内指定ETF的份额数据（按日逐日获取后合并）。

        注意：份额API按日期查询全市场，逐日获取可能较慢。
        建议先获取交易日历，再对每个交易日调用。

        Returns:
            DataFrame with columns: date, code, share_total
        """
        target_codes = set(codes or get_all_etf_codes())

        # 获取交易日历
        cal_result = self.fetch_trading_calendar()
        if cal_result.data.empty:
            logger.warning("交易日历不可用，使用工作日近似")
            dates = pd.bdate_range(start=start_date, end=end_date)
        else:
            cal = cal_result.data.copy()
            cal["trade_date"] = pd.to_datetime(cal["trade_date"])
            mask = (cal["trade_date"] >= start_date) & (cal["trade_date"] <= end_date)
            dates = cal[mask]["trade_date"].tolist()

        all_shares = []
        total = len(dates)
        for i, d in enumerate(dates, 1):
            date_str = pd.to_datetime(d).strftime("%Y%m%d")
            if i % 20 == 1 or i == total:
                print(f"  份额数据 [{i}/{total}] {date_str}...", flush=True)

            result = self.fetch_etf_shares(date_str)
            if not result.data.empty:
                filtered = result.data[result.data["code"].isin(target_codes)]
                if not filtered.empty:
                    all_shares.append(filtered)

        if all_shares:
            combined = pd.concat(all_shares, ignore_index=True)
            combined["date"] = pd.to_datetime(combined["date"])
            combined.sort_values(["code", "date"], inplace=True)
            combined.reset_index(drop=True, inplace=True)
            print(f"  份额数据完成! {len(combined)}条记录")
            return combined

        print("  份额数据为空")
        return pd.DataFrame()

    # ──────────────────────────────────────────
    # 数据合并：将份额数据拼接到日线中
    # ──────────────────────────────────────────

    def merge_shares_into_daily(
        self,
        daily_data: Dict[str, pd.DataFrame],
        shares_data: pd.DataFrame,
    ) -> Dict[str, pd.DataFrame]:
        """将份额数据左连接到每只ETF的日线数据中。"""
        if shares_data.empty:
            for code, df in daily_data.items():
                if "share_total" not in df.columns:
                    df["share_total"] = pd.NA
            return daily_data

        shares_data["date"] = pd.to_datetime(shares_data["date"])

        for code, df in daily_data.items():
            code_shares = shares_data[shares_data["code"] == code][["date", "share_total"]].copy()
            if code_shares.empty:
                df["share_total"] = pd.NA
                continue

            df["date"] = pd.to_datetime(df["date"])
            # 先删除旧的share_total列（如果存在）
            if "share_total" in df.columns:
                df.drop(columns=["share_total"], inplace=True)
            df = df.merge(code_shares, on="date", how="left")
            df["share_total"] = df["share_total"].ffill()
            daily_data[code] = df

        return daily_data

    # ──────────────────────────────────────────
    # 诊断
    # ──────────────────────────────────────────

    def diagnose(self) -> Dict[str, str]:
        """诊断所有数据源可用性，返回检查结果字典。"""
        results = {}

        # 1. AKShare连通性
        status = self._probe_source()
        results["akshare_status"] = f"{'[PASS]' if status.available else '[FAIL]'} {status.message}"

        # 2. ETF日线行情
        try:
            test = fetch_etf_daily_akshare("510300", "20250101", "20250110")
            results["etf_daily"] = f"[PASS] {len(test)} rows" if not test.empty else "[FAIL] empty"
        except Exception as e:
            results["etf_daily"] = f"[FAIL] {e}"

        # 3. ETF shares
        try:
            test = fetch_etf_shares_akshare("20250110")
            results["etf_shares"] = f"[PASS] {len(test)} rows" if not test.empty else "[FAIL] empty"
        except Exception as e:
            results["etf_shares"] = f"[FAIL] {e}"

        # 4. Fund NAV
        try:
            test = fetch_etf_nav_akshare("510300")
            results["etf_nav"] = f"[PASS] {len(test)} rows" if not test.empty else "[FAIL] empty"
        except Exception as e:
            results["etf_nav"] = f"[FAIL] {e}"

        # 5. Trading calendar
        try:
            test = fetch_trading_calendar_akshare()
            results["trading_calendar"] = f"[PASS] {len(test)} rows" if not test.empty else "[FAIL] empty"
        except Exception as e:
            results["trading_calendar"] = f"[FAIL] {e}"

        # 6. Index data
        try:
            test = fetch_index_daily_akshare("000300", "20250101", "20250110")
            results["index_daily"] = f"[PASS] {len(test)} rows" if not test.empty else "[FAIL] empty"
        except Exception as e:
            results["index_daily"] = f"[FAIL] {e}"

        return results
