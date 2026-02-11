"""数据处理与指标计算工具（v2.0）。

包含PRD v2.0定义的全部因子计算：
- 基础收益率/波动率
- 资金流强度(MFI) + 资金流加速度(MFA)
- 折溢价行为指数(PDI) + 盘中溢价代理
- 多周期动量(CMC)
- 估值分位代理
- 滚动Z-score标准化（2.2节）
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config.strategy_config import SIGNAL_CONFIG


# ──────────────────────────────────────────────
# 通用标准化函数（PRD 2.2节）
# ──────────────────────────────────────────────

def standardize(
    series: pd.Series,
    window: int | None = None,
    min_periods: int = 20,
) -> pd.Series:
    """滚动Z-score标准化，结果经Winsorize限制在[-3, +3]。

    Args:
        series: 原始因子值序列
        window: 滚动窗口天数，默认从配置读取（60个交易日）
        min_periods: 最少计算期数

    Returns:
        标准化后的因子值，范围约(-3, +3)
    """
    if window is None:
        window = SIGNAL_CONFIG["lookback"].get("standardize_window", 60)

    rolling_mean = series.rolling(window, min_periods=min_periods).mean()
    rolling_std = series.rolling(window, min_periods=min_periods).std()
    z_score = (series - rolling_mean) / rolling_std.clip(lower=1e-8)
    return z_score.clip(-3, 3)


class DataProcessor:
    """负责计算资金流、溢价行为、动量等衍生指标。"""

    @staticmethod
    def clean_daily_data(df: pd.DataFrame) -> pd.DataFrame:
        """基础清洗：排序、去重、缺失填充。"""
        if df.empty:
            return df

        out = df.copy()
        out["date"] = pd.to_datetime(out["date"])
        out.sort_values("date", inplace=True)
        out.drop_duplicates(subset=["date", "code"], inplace=True)

        num_cols = [
            "open", "high", "low", "close", "volume", "amount",
            "share_total", "nav", "premium_rate",
        ]
        for col in num_cols:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")

        # 前向填充
        out["close"] = out["close"].ffill()
        out["open"] = out["open"].fillna(out["close"])
        out["high"] = out["high"].fillna(out["close"])
        out["low"] = out["low"].fillna(out["close"])
        out["volume"] = out["volume"].fillna(0)
        out["amount"] = out["amount"].fillna(out["close"] * out["volume"])

        if "share_total" in out.columns:
            out["share_total"] = out["share_total"].ffill().bfill()

        if "nav" in out.columns:
            out["nav"] = out["nav"].ffill().bfill()
            out["nav"] = out["nav"].fillna(out["close"])
        else:
            out["nav"] = out["close"]

        # 溢价率
        if "premium_rate" not in out.columns or out["premium_rate"].isna().all():
            out["premium_rate"] = (out["close"] - out["nav"]) / out["nav"] * 100
        else:
            calc = (out["close"] - out["nav"]) / out["nav"] * 100
            out["premium_rate"] = out["premium_rate"].fillna(calc)

        out.reset_index(drop=True, inplace=True)
        return out

    # ──────────────────────────────────────────
    # 收益率 & 波动率
    # ──────────────────────────────────────────

    @staticmethod
    def add_return_features(df: pd.DataFrame) -> pd.DataFrame:
        """计算收益率和波动率特征。"""
        if df.empty:
            return df

        out = df.copy()
        out["ret_1d"] = out["close"].pct_change()
        out["ret_5d"] = out["close"].pct_change(5)
        out["ret_10d"] = out["close"].pct_change(10)
        out["ret_20d"] = out["close"].pct_change(20)
        out["vol_20d"] = out["ret_1d"].rolling(20).std() * np.sqrt(252)

        # 多周期动量 CMC
        out["cmc"] = (out["ret_5d"] * 0.5 + out["ret_20d"] * 0.5) / out["vol_20d"].replace(0, np.nan)
        return out

    # ──────────────────────────────────────────
    # 资金流强度(MFI) + 资金流加速度(MFA)
    # ──────────────────────────────────────────

    @staticmethod
    def add_fund_flow_features(df: pd.DataFrame) -> pd.DataFrame:
        """计算资金净流入、资金流强度(MFI)和资金流加速度(MFA)。"""
        if df.empty:
            return df

        out = df.copy()

        # 资金净流入 = 份额变动 × 收盘价
        if "share_total" in out.columns and not out["share_total"].isna().all():
            share_change = out["share_total"].diff()
            out["net_inflow"] = share_change * out["close"]
        else:
            out["net_inflow"] = 0.0

        # MFI: 近5日累计净流入 / 近5日日均成交额 × 100
        amount_mean_5 = out["amount"].rolling(5).mean().replace(0, np.nan)
        out["mfi"] = out["net_inflow"].rolling(5).sum() / amount_mean_5 * 100

        # 行业资金流强度: 近3日
        amount_mean_3 = out["amount"].rolling(3).mean().replace(0, np.nan)
        out["sector_flow_strength"] = out["net_inflow"].rolling(3).sum() / amount_mean_3 * 100

        # 资金流加速度 MFA: (近3日MFI - 前3日MFI) / |前3日MFI|
        mfi_recent = out["mfi"].rolling(3).mean()
        mfi_prev = out["mfi"].shift(3).rolling(3).mean()
        out["mfa"] = (mfi_recent - mfi_prev) / mfi_prev.abs().clip(lower=1e-8)

        return out

    # ──────────────────────────────────────────
    # 折溢价行为指数(PDI)
    # ──────────────────────────────────────────

    @staticmethod
    def add_pdi_features(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
        """计算折溢价行为指数PDI（-100 到 +100）。"""
        if df.empty:
            return df

        out = df.copy()
        min_prem = out["premium_rate"].rolling(window).min()
        max_prem = out["premium_rate"].rolling(window).max()
        range_prem = (max_prem - min_prem).replace(0, np.nan)
        out["pdi"] = (out["premium_rate"] - min_prem) / range_prem * 200 - 100
        out["pdi"] = out["pdi"].clip(-100, 100)
        return out

    # ──────────────────────────────────────────
    # 盘中溢价代理
    # ──────────────────────────────────────────

    @staticmethod
    def add_intraday_premium_proxy(df: pd.DataFrame) -> pd.DataFrame:
        """计算盘中溢价代理指标。

        理想情况: 盘中溢价变化 = 收盘溢价率 - 开盘溢价率
        但日线数据无盘中IOPV，故用收盘溢价率的日间变化近似:
            intraday_premium_proxy = 今日溢价率 - 昨日溢价率
        """
        if df.empty:
            return df

        out = df.copy()
        out["intraday_premium_proxy"] = out["premium_rate"].diff()
        return out

    # ──────────────────────────────────────────
    # 估值分位代理
    # ──────────────────────────────────────────

    @staticmethod
    def add_valuation_proxy(df: pd.DataFrame, window: int = 252) -> pd.DataFrame:
        """无估值数据时，用价格分位近似估值分位。"""
        if df.empty:
            return df

        out = df.copy()

        def calc_percentile(s: pd.Series) -> float:
            current = s.iloc[-1]
            return float((s <= current).sum() / len(s))

        out["valuation_pct"] = (
            out["close"]
            .rolling(window, min_periods=20)
            .apply(calc_percentile, raw=False)
        )
        return out

    # ──────────────────────────────────────────
    # Z-score标准化列
    # ──────────────────────────────────────────

    @staticmethod
    def add_standardized_scores(df: pd.DataFrame) -> pd.DataFrame:
        """对关键因子列做滚动Z-score标准化，生成 _z 后缀列。"""
        if df.empty:
            return df

        out = df.copy()
        cols_to_standardize = [
            "mfi", "mfa", "pdi", "cmc",
            "sector_flow_strength",
            "intraday_premium_proxy",
            "valuation_pct",
            "premium_rate",
        ]

        for col in cols_to_standardize:
            if col in out.columns and not out[col].isna().all():
                out[f"{col}_z"] = standardize(out[col])

        return out

    # ──────────────────────────────────────────
    # 全流程处理
    # ──────────────────────────────────────────

    @classmethod
    def process(cls, df: pd.DataFrame) -> pd.DataFrame:
        """执行全流程数据处理: 清洗 → 收益 → 资金流 → PDI → 溢价代理 → 估值 → 标准化。"""
        out = cls.clean_daily_data(df)
        out = cls.add_return_features(out)
        out = cls.add_fund_flow_features(out)
        out = cls.add_pdi_features(out)
        out = cls.add_intraday_premium_proxy(out)
        out = cls.add_valuation_proxy(out)
        out = cls.add_standardized_scores(out)
        return out
