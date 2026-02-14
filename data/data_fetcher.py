"""统一数据获取入口。

职责：
1. 协调 Tushare Pro API调用与本地缓存
2. 合并行情、份额、净值为完整数据集
3. 提供带进度显示的批量获取
4. 数据源可用性诊断

注意: 仅支持 Tushare Pro (需要token) 和 Mock 回退
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable, TypeVar, Any
from functools import wraps

import pandas as pd

from config.strategy_config import BACKTEST_CONFIG
from config.etf_pool import get_all_etf_codes, get_broad_codes, get_sector_codes, BENCHMARK_INDICES
from data.cache_manager import CacheManager
from data.data_sources import (
    DataSourceStatus,
    probe_tushare,
    fetch_etf_daily_tushare,
    fetch_etf_shares_tushare,
    fetch_etf_nav_tushare,
    fetch_trading_calendar_tushare,
    fetch_index_daily_tushare,
    fetch_stk_factor_pro_tushare,
    generate_mock_etf_data,
    set_tushare_token,
)

logger = logging.getLogger(__name__)

# 类型变量用于泛型
T = TypeVar('T')


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器：在失败时自动重试。

    Args:
        max_retries: 最大重试次数
        delay: 每次重试之间的延迟（秒）
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc
                    if attempt < max_retries:
                        wait_time = delay * (2 ** attempt)  # 指数退避
                        logger.warning(f"{func.__name__} 失败 (尝试 {attempt + 1}/{max_retries + 1}): {exc}, {wait_time:.1f}s后重试...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"{func.__name__} 失败，已重试 {max_retries} 次: {exc}")
            raise last_exception
        return wrapper
    return decorator


@dataclass
class FetchResult:
    data: pd.DataFrame
    source: str
    message: str


class DataFetcher:
    """统一数据获取入口，优先缓存 → Tushare → Mock回退。"""

    def __init__(
        self,
        fallback_to_mock: bool = True,
        cache_dir: Optional[str] = None,
        api_delay: float = 0.5,
        tushare_token: Optional[str] = None,
    ):
        self.fallback_to_mock = fallback_to_mock
        self.cache = CacheManager(cache_dir)
        self.api_delay = api_delay  # API调用间隔（秒），防止被限频

        # Tushare token 初始化
        if tushare_token:
            set_tushare_token(tushare_token)

        self.source_status = self._probe_source()

    def _probe_source(self) -> DataSourceStatus:
        return probe_tushare()

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
        """获取单个ETF日线数据，优先读缓存，支持3次重试。"""
        start_dt = pd.Timestamp(start_date)
        cache_hit = False

        if use_cache:
            cached = self.cache.read("etf_daily", code)
            if cached is not None and not cached.empty:
                cached["date"] = pd.to_datetime(cached["date"])
                # 检查缓存是否覆盖了请求的起始日期（允许3天误差，考虑节假日）
                cache_start = cached["date"].min()
                if cache_start <= start_dt + pd.Timedelta(days=3):
                    # 缓存覆盖了请求范围（含节假日容差）
                    mask = (cached["date"] >= start_date) & (cached["date"] <= end_date)
                    filtered = cached[mask].copy()
                    if not filtered.empty:
                        cache_hit = True
                        return FetchResult(filtered, "cache", f"缓存命中 {len(filtered)}条")

        # 缓存未命中或不使用缓存，从 API 获取（带3次重试）
        if not cache_hit and self.source_status.available:
            try:
                df = self._fetch_etf_daily_with_retry(code, start_date, end_date)
                if not df.empty:
                    self.cache.append("etf_daily", code, df)
                    self._api_sleep()
                    return FetchResult(df, "tushare", f"真实数据 {len(df)}条")
            except Exception as exc:
                logger.warning(f"Tushare获取失败 ({code}): {exc}")
                if not self.fallback_to_mock:
                    raise

        if self.fallback_to_mock:
            mock = generate_mock_etf_data(code, start_date, end_date)
            return FetchResult(mock, "mock", "模拟数据")

        raise RuntimeError(f"数据源不可用且未启用mock: {code}")

    @retry_on_failure(max_retries=3, delay=1.0)
    def _fetch_etf_daily_with_retry(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """带重试机制的ETF日线数据获取。"""
        return fetch_etf_daily_tushare(code, start_date, end_date)

    # ──────────────────────────────────────────
    # ETF份额数据（带3次重试）
    # ──────────────────────────────────────────

    def fetch_etf_shares_for_period(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """获取一段时间内指定ETF的份额数据（带缓存和重试）。

        Returns:
            DataFrame with columns: date, code, share_total
        """
        target_codes = list(codes or get_all_etf_codes())

        # 尝试从缓存读取
        cached = self.cache.read("shares", "all")
        if cached is not None and not cached.empty:
            cached["date"] = pd.to_datetime(cached["date"])
            # 检查缓存是否覆盖请求范围
            cache_start = cached["date"].min()
            cache_end = cached["date"].max()
            request_start = pd.Timestamp(start_date)
            request_end = pd.Timestamp(end_date)

            if cache_start <= request_start + pd.Timedelta(days=3) and cache_end >= request_end - pd.Timedelta(days=3):
                # 缓存覆盖范围，筛选数据
                cached_codes = set(cached["code"].unique())
                requested_codes = set(target_codes)

                if requested_codes.issubset(cached_codes):
                    mask = (cached["date"] >= start_date) & (cached["date"] <= end_date) & \
                           (cached["code"].isin(target_codes))
                    filtered = cached[mask].copy()
                    if not filtered.empty:
                        print(f"  份额数据缓存命中 {len(filtered)}条")
                        return filtered

        if self.source_status.available:
            print(f"  使用Tushare获取份额数据 ({len(target_codes)}只ETF)...")
            try:
                df = self._fetch_shares_with_retry(target_codes, start_date, end_date)
                if not df.empty:
                    # 保存到缓存（使用append增量合并）
                    self.cache.append("shares", "all", df)
                    print(f"  份额数据完成! {len(df)}条记录（已缓存）")
                    return df
                else:
                    print("  Tushare份额数据为空")
            except Exception as exc:
                logger.warning(f"Tushare份额获取失败: {exc}")
                print(f"  Tushare份额获取失败: {exc}")

        print("  份额数据为空")
        return pd.DataFrame()

    @retry_on_failure(max_retries=3, delay=1.0)
    def _fetch_shares_with_retry(
        self, codes: List[str], start_date: str, end_date: str
    ) -> pd.DataFrame:
        """带重试机制的份额数据获取。"""
        return fetch_etf_shares_tushare(codes, start_date, end_date)

    # ──────────────────────────────────────────
    # 基金净值（IOPV替代，带3次重试）
    # ──────────────────────────────────────────

    def fetch_etf_nav(self, code: str, use_cache: bool = True) -> FetchResult:
        """获取ETF历史净值序列（带3次重试）。"""
        if use_cache:
            cached = self.cache.read("nav", code)
            if cached is not None and not cached.empty:
                return FetchResult(cached, "cache", f"净值缓存命中 {len(cached)}条")

        if self.source_status.available:
            try:
                df = self._fetch_nav_with_retry(code)
                if not df.empty:
                    self.cache.write("nav", code, df)
                    return FetchResult(df, "tushare", f"净值数据 {len(df)}条")
            except Exception as exc:
                logger.warning(f"净值数据获取失败 ({code}): {exc}")

        return FetchResult(pd.DataFrame(), "none", "净值数据不可用")

    @retry_on_failure(max_retries=3, delay=1.0)
    def _fetch_nav_with_retry(self, code: str) -> pd.DataFrame:
        """带重试机制的净值数据获取。"""
        self._api_sleep()
        return fetch_etf_nav_tushare(code)

    # ──────────────────────────────────────────
    # 指数日线（带3次重试）
    # ──────────────────────────────────────────

    def fetch_index(
        self, code: str, start_date: str, end_date: str, use_cache: bool = True
    ) -> FetchResult:
        """获取指数日线行情（带3次重试）。"""
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
                df = self._fetch_index_with_retry(code, start_date, end_date)
                if not df.empty:
                    self.cache.append("index", code, df)
                    return FetchResult(df, "tushare", f"指数数据 {len(df)}条")
            except Exception as exc:
                logger.warning(f"指数数据获取失败 ({code}): {exc}")

        return FetchResult(pd.DataFrame(), "none", "指数数据不可用")

    @retry_on_failure(max_retries=3, delay=1.0)
    def _fetch_index_with_retry(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """带重试机制的指数数据获取。"""
        self._api_sleep()
        return fetch_index_daily_tushare(code, start_date, end_date)

    # ──────────────────────────────────────────
    # 交易日历（带3次重试）
    # ──────────────────────────────────────────

    def fetch_trading_calendar(self) -> FetchResult:
        """获取交易日历（带3次重试）。"""
        cached = self.cache.read("calendar", "trade_dates")
        if cached is not None and not cached.empty:
            return FetchResult(cached, "cache", f"日历缓存命中 {len(cached)}条")

        if self.source_status.available:
            try:
                df = self._fetch_calendar_with_retry()
                if not df.empty:
                    self.cache.write("calendar", "trade_dates", df)
                    return FetchResult(df, "tushare", f"交易日历 {len(df)}条")
            except Exception as exc:
                logger.warning(f"交易日历获取失败: {exc}")

        return FetchResult(pd.DataFrame(), "none", "交易日历不可用")

    @retry_on_failure(max_retries=3, delay=1.0)
    def _fetch_calendar_with_retry(self) -> pd.DataFrame:
        """带重试机制的交易日历获取。"""
        return fetch_trading_calendar_tushare()

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
            print(f"[OK] ({status}, {len(df)} rows)")

        print(f"\nDone! Got {len(result)} ETFs")
        return result

    def fetch_shares_for_period(
        self,
        start_date: str,
        end_date: str,
        codes: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """获取一段时间内指定ETF的份额数据。

        Returns:
            DataFrame with columns: date, code, share_total
        """
        return self.fetch_etf_shares_for_period(
            codes=codes or get_all_etf_codes(),
            start_date=start_date,
            end_date=end_date,
        )

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
    # 技术面因子数据（MACD、均线等，带3次重试）
    # ──────────────────────────────────────────

    def fetch_tech_factors_for_period(
        self,
        start_date: str,
        end_date: str,
        codes: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """获取多只ETF的技术面因子数据（带重试）。

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            codes: ETF代码列表，默认全部ETF池

        Returns:
            DataFrame with columns: date, code, macd, macd_dea, macd_dif,
                                   ma5, ma10, ma20, ma60, etc.
        """
        codes = codes or get_all_etf_codes()
        print(f"  使用Tushare获取技术因子数据 ({len(codes)}只ETF)...")

        all_parts = []
        for i, code in enumerate(codes):
            try:
                result = self._fetch_tech_factor_with_retry(code, start_date, end_date)
                if not result.empty:
                    all_parts.append(result)
                if (i + 1) % 10 == 0:
                    print(f"    进度: {i+1}/{len(codes)}")
            except Exception as exc:
                logger.warning(f"技术因子获取失败 ({code}): {exc}")
                continue

        if not all_parts:
            return pd.DataFrame()

        combined = pd.concat(all_parts, ignore_index=True)
        print(f"  技术因子数据完成! {len(combined)}条记录")
        return combined

    @retry_on_failure(max_retries=3, delay=1.0)
    def _fetch_tech_factor_with_retry(
        self, code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """带重试机制的技术因子数据获取。"""
        result = fetch_stk_factor_pro_tushare(code, start_date, end_date)
        self._api_sleep()
        return result

    def merge_tech_factors_into_daily(
        self,
        daily_data: Dict[str, pd.DataFrame],
        tech_data: pd.DataFrame,
    ) -> Dict[str, pd.DataFrame]:
        """将技术因子数据左连接到每只ETF的日线数据中。"""
        if tech_data.empty:
            return daily_data

        tech_data["date"] = pd.to_datetime(tech_data["date"])

        # 需要合并的技术因子列
        factor_cols = ["macd", "macd_dea", "macd_dif",
                       "ma5", "ma10", "ma20", "ma60",
                       "rsi_6", "rsi_12", "kdj_k", "kdj_d", "kdj_j", "vol_ratio"]

        for code, df in daily_data.items():
            code_factors = tech_data[tech_data["code"] == code].copy()
            if code_factors.empty:
                continue

            df["date"] = pd.to_datetime(df["date"])

            # 删除旧的技术因子列（如果存在）
            for col in factor_cols:
                if col in df.columns:
                    df.drop(columns=[col], inplace=True)

            # 合并数据
            merge_cols = ["date"] + [c for c in factor_cols if c in code_factors.columns]
            df = df.merge(code_factors[merge_cols], on="date", how="left")
            daily_data[code] = df

        return daily_data

    # ──────────────────────────────────────────
    # 净值数据（用于PDI因子计算）
    # ──────────────────────────────────────────

    def fetch_nav_for_period(
        self,
        start_date: str,
        end_date: str,
        codes: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """获取一段时间内指定ETF的净值数据（带缓存和重试）。

        Returns:
            DataFrame with columns: date, code, nav
        """
        codes = codes or get_all_etf_codes()

        # 尝试从缓存读取
        cached = self.cache.read("nav", "all")
        if cached is not None and not cached.empty:
            cached["date"] = pd.to_datetime(cached["date"])
            cache_start = cached["date"].min()
            cache_end = cached["date"].max()
            request_start = pd.Timestamp(start_date)
            request_end = pd.Timestamp(end_date)

            if cache_start <= request_start + pd.Timedelta(days=3) and cache_end >= request_end - pd.Timedelta(days=3):
                cached_codes = set(cached["code"].unique())
                requested_codes = set(codes)

                if requested_codes.issubset(cached_codes):
                    mask = (cached["date"] >= start_date) & (cached["date"] <= end_date) & \
                           (cached["code"].isin(codes))
                    filtered = cached[mask].copy()
                    if not filtered.empty:
                        print(f"  净值数据缓存命中 {len(filtered)}条")
                        return filtered

        if self.source_status.available:
            print(f"  使用Tushare获取净值数据 ({len(codes)}只ETF)...")
            try:
                df = self._fetch_nav_batch_with_retry(codes, start_date, end_date)
                if not df.empty:
                    self.cache.append("nav", "all", df)
                    print(f"  净值数据完成! {len(df)}条记录（已缓存）")
                    return df
                else:
                    print("  Tushare净值数据为空")
            except Exception as exc:
                logger.warning(f"Tushare净值获取失败: {exc}")
                print(f"  Tushare净值获取失败: {exc}")

        print("  净值数据为空")
        return pd.DataFrame()

    @retry_on_failure(max_retries=3, delay=1.0)
    def _fetch_nav_batch_with_retry(
        self, codes: List[str], start_date: str, end_date: str
    ) -> pd.DataFrame:
        """带重试机制的批量净值数据获取。"""
        all_parts = []
        for i, code in enumerate(codes):
            try:
                result = fetch_etf_nav_tushare(code)
                if not result.empty:
                    # 筛选日期范围
                    result["date"] = pd.to_datetime(result["date"])
                    mask = (result["date"] >= start_date) & (result["date"] <= end_date)
                    filtered = result[mask].copy()
                    if not filtered.empty:
                        all_parts.append(filtered)
                if (i + 1) % 10 == 0:
                    print(f"    净值进度: {i+1}/{len(codes)}")
                self._api_sleep()
            except Exception as exc:
                logger.warning(f"获取净值失败 ({code}): {exc}")
                continue

        if not all_parts:
            return pd.DataFrame()

        combined = pd.concat(all_parts, ignore_index=True)
        return combined

    def merge_nav_into_daily(
        self,
        daily_data: Dict[str, pd.DataFrame],
        nav_data: pd.DataFrame,
    ) -> Dict[str, pd.DataFrame]:
        """将净值数据左连接到每只ETF的日线数据中。"""
        if nav_data.empty:
            for code, df in daily_data.items():
                if "nav" not in df.columns:
                    df["nav"] = df["close"]  # 回退: 用收盘价
            return daily_data

        nav_data["date"] = pd.to_datetime(nav_data["date"])

        for code, df in daily_data.items():
            code_nav = nav_data[nav_data["code"] == code][["date", "nav"]].copy()
            if code_nav.empty:
                # 没有净值数据，使用收盘价
                if "nav" not in df.columns:
                    df["nav"] = df["close"]
                continue

            df["date"] = pd.to_datetime(df["date"])
            # 先删除旧的nav列（如果存在）
            if "nav" in df.columns:
                df.drop(columns=["nav"], inplace=True)
            df = df.merge(code_nav, on="date", how="left")
            df["nav"] = df["nav"].ffill().bfill()
            # 如果还有缺失，用收盘价填充
            df["nav"] = df["nav"].fillna(df["close"])
            daily_data[code] = df

        return daily_data
    # ──────────────────────────────────────────

    def diagnose(self) -> Dict[str, str]:
        """诊断所有数据源可用性，返回检查结果字典。"""
        results = {}

        # 1. Tushare连通性
        status = self._probe_source()
        results["tushare_status"] = f"{'[PASS]' if status.available else '[FAIL]'} {status.message}"

        # 2. ETF日线行情
        try:
            test = fetch_etf_daily_tushare("510300", "20250101", "20250110")
            results["etf_daily"] = f"[PASS] {len(test)} rows" if not test.empty else "[FAIL] empty"
        except Exception as e:
            results["etf_daily"] = f"[FAIL] {e}"

        # 3. ETF shares
        try:
            test = fetch_etf_shares_tushare(["510300"], "20250101", "20250110")
            results["etf_shares"] = f"[PASS] {len(test)} rows" if not test.empty else "[FAIL] empty"
        except Exception as e:
            results["etf_shares"] = f"[FAIL] {e}"

        # 4. Fund NAV
        try:
            test = fetch_etf_nav_tushare("510300")
            results["etf_nav"] = f"[PASS] {len(test)} rows" if not test.empty else "[FAIL] empty"
        except Exception as e:
            results["etf_nav"] = f"[FAIL] {e}"

        # 5. Trading calendar
        try:
            test = fetch_trading_calendar_tushare()
            results["trading_calendar"] = f"[PASS] {len(test)} rows" if not test.empty else "[FAIL] empty"
        except Exception as e:
            results["trading_calendar"] = f"[FAIL] {e}"

        # 6. Index data
        try:
            test = fetch_index_daily_tushare("000300", "20250101", "20250110")
            results["index_daily"] = f"[PASS] {len(test)} rows" if not test.empty else "[FAIL] empty"
        except Exception as e:
            results["index_daily"] = f"[FAIL] {e}"

        return results
