"""数据模块。

包含:
- DataFetcher: 统一数据获取入口
- DataProcessor: 指标计算
- CacheManager: 本地CSV缓存
- data_sources: AKShare API封装
- standardize: 滚动Z-score标准化
"""

from data.data_fetcher import DataFetcher, FetchResult
from data.data_processor import DataProcessor, standardize
from data.cache_manager import CacheManager
from data.data_sources import DataSourceStatus

__all__ = [
    "DataFetcher",
    "FetchResult",
    "DataProcessor",
    "standardize",
    "CacheManager",
    "DataSourceStatus",
]
