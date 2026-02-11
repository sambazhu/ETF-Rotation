"""本地CSV缓存管理器。

避免重复调用AKShare API，支持按日期增量更新。
缓存存储在 data/cache/ 目录下，按数据类型和ETF代码组织。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd


class CacheManager:
    """管理本地CSV文件缓存。"""

    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir is None:
            cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, category: str, key: str) -> Path:
        """构造缓存文件路径: cache/{category}/{key}.csv"""
        category_dir = self.cache_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)
        return category_dir / f"{key}.csv"

    def read(self, category: str, key: str) -> Optional[pd.DataFrame]:
        """读取缓存，不存在则返回None。"""
        path = self._get_cache_path(category, key)
        if not path.exists():
            return None
        try:
            df = pd.read_csv(path, parse_dates=["date"])
            return df
        except Exception:
            return None

    def write(self, category: str, key: str, data: pd.DataFrame) -> None:
        """写入缓存（覆盖模式）。"""
        if data.empty:
            return
        path = self._get_cache_path(category, key)
        data.to_csv(path, index=False)

    def append(self, category: str, key: str, new_data: pd.DataFrame) -> pd.DataFrame:
        """增量追加：与已有缓存合并去重后写入，返回合并结果。"""
        existing = self.read(category, key)
        if existing is not None and not existing.empty:
            combined = pd.concat([existing, new_data], ignore_index=True)
            if "date" in combined.columns:
                combined["date"] = pd.to_datetime(combined["date"])
                dedup_cols = ["date"]
                if "code" in combined.columns:
                    dedup_cols.append("code")
                combined.drop_duplicates(subset=dedup_cols, keep="last", inplace=True)
                combined.sort_values("date", inplace=True)
            combined.reset_index(drop=True, inplace=True)
        else:
            combined = new_data.copy()

        self.write(category, key, combined)
        return combined

    def get_latest_date(self, category: str, key: str) -> Optional[str]:
        """获取缓存中最新的日期，用于增量更新起点。"""
        df = self.read(category, key)
        if df is None or df.empty or "date" not in df.columns:
            return None
        return str(pd.to_datetime(df["date"]).max().date())

    def is_stale(self, category: str, key: str, max_age_hours: int = 16) -> bool:
        """检查缓存是否过期（默认16小时，即次日需要重新获取）。"""
        path = self._get_cache_path(category, key)
        if not path.exists():
            return True
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return datetime.now() - mtime > timedelta(hours=max_age_hours)

    def clear(self, category: Optional[str] = None) -> int:
        """清除缓存。指定category则只清该目录，否则全清。返回清除文件数。"""
        count = 0
        if category:
            target = self.cache_dir / category
        else:
            target = self.cache_dir

        if target.exists():
            for f in target.rglob("*.csv"):
                f.unlink()
                count += 1
        return count
