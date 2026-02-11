"""ETF标的池配置（v2.0）。

设计原则：
- 宽基池仅包含覆盖面广的宽基指数和风格指数ETF，不含单一行业/主题ETF
- 行业池覆盖科技/新能源/消费/医药/金融/周期/高端制造/主题等赛道
- 两个池子之间不存在代码重叠，避免仓位重叠风险
"""

from __future__ import annotations

from typing import Dict, List


BROAD_BASED_ETF_POOL: List[Dict[str, str]] = [
    {"code": "510300", "name": "沪深300", "style": "大盘价值", "scope": "大盘蓝筹"},
    {"code": "159601", "name": "中证A50", "style": "大盘核心", "scope": "各行业龙头50只"},
    {"code": "510500", "name": "中证500", "style": "中盘", "scope": "中盘成长"},
    {"code": "512100", "name": "中证1000", "style": "小盘", "scope": "小盘股票"},
    {"code": "159537", "name": "国证2000", "style": "微盘", "scope": "微盘股覆盖"},
    {"code": "588000", "name": "科创50", "style": "科技成长", "scope": "科创板科技"},
    {"code": "159915", "name": "创业板", "style": "成长", "scope": "创业板成长股"},
    {"code": "512890", "name": "红利低波", "style": "价值防御", "scope": "高股息低波动"},
    {"code": "512000", "name": "券商", "style": "弹性", "scope": "市场Beta"},
    {"code": "515000", "name": "科技", "style": "科技主题", "scope": "科技板块"},
]


SECTOR_ETF_POOL: List[Dict[str, str]] = [
    {"code": "512480", "name": "半导体", "category": "科技"},
    {"code": "159819", "name": "人工智能", "category": "科技"},
    {"code": "512760", "name": "芯片", "category": "科技"},
    {"code": "562500", "name": "机器人", "category": "科技"},
    {"code": "515700", "name": "光伏", "category": "新能源"},
    {"code": "516160", "name": "储能", "category": "新能源"},
    {"code": "512690", "name": "白酒", "category": "消费"},
    {"code": "159928", "name": "消费", "category": "消费"},
    {"code": "512010", "name": "医药", "category": "医药"},
    {"code": "512170", "name": "医疗", "category": "医药"},
    {"code": "512880", "name": "证券", "category": "金融"},
    {"code": "512070", "name": "银行", "category": "金融"},
    {"code": "512400", "name": "有色金属", "category": "周期"},
    {"code": "512200", "name": "房地产", "category": "周期"},
    {"code": "560660", "name": "工业母机", "category": "高端制造"},
    {"code": "159790", "name": "电池", "category": "新能源"},
    {"code": "515220", "name": "煤炭", "category": "周期"},
    {"code": "516950", "name": "基建", "category": "周期"},
    {"code": "512660", "name": "军工", "category": "主题"},
    {"code": "512680", "name": "家电", "category": "消费"},
]


# 用于基准对比的指数代码
BENCHMARK_INDICES = {
    "000300": "沪深300",
    "000905": "中证500",
    "000852": "中证1000",
    "000906": "中证800",   # 行业相对动量的基准
}


def get_all_etf_codes() -> List[str]:
    """返回宽基池和行业池合并后的去重代码列表。"""
    code_set = {item["code"] for item in BROAD_BASED_ETF_POOL}
    code_set.update(item["code"] for item in SECTOR_ETF_POOL)
    return sorted(code_set)


def get_broad_codes() -> List[str]:
    """返回宽基池代码列表。"""
    return [item["code"] for item in BROAD_BASED_ETF_POOL]


def get_sector_codes() -> List[str]:
    """返回行业池代码列表。"""
    return [item["code"] for item in SECTOR_ETF_POOL]
