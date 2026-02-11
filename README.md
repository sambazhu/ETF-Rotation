# 资金驱动ETF轮动策略交易系统

基于ETF资金流、折溢价行为和动量因子的三层量化轮动策略，含完整回测引擎和可视化报告。

## 系统架构

```
            ┌─────────────────────────────┐
            │     第一层: 宏观仓位判断       │
            │  (5因子 → Sigmoid → 0~100%)  │
            └──────────┬──────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                        ▼
┌──────────────────┐    ┌──────────────────┐
│ 第二层: 宽基轮动   │    │ 第三层: 行业轮动   │
│ (4因子 Z-score)   │    │ (5因子 + 过热滤波) │
└────────┬─────────┘    └────────┬─────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
         ┌──────────────────────┐
         │  组合管理 + 风控引擎   │
         │ (止损/止盈/冷却/圆整)  │
         └──────────────────────┘
```

## 目录结构

```
├── config/                         # 配置
│   ├── etf_pool.py                # ETF标的池 (30只)
│   └── strategy_config.py         # 策略/回测/风控参数
├── data/                           # 数据层
│   ├── data_fetcher.py            # 统一数据获取 (AKShare + 缓存 + Mock)
│   ├── data_processor.py          # 指标计算 + Z-score标准化
│   ├── data_sources.py            # AKShare/Mock数据源
│   └── cache_manager.py           # Parquet本地缓存
├── strategy/                       # 信号层
│   ├── macro_signal.py            # 宏观仓位 (5因子Sigmoid)
│   ├── broad_based_rotation.py    # 宽基轮动 (4因子排序)
│   ├── sector_rotation.py         # 行业轮动 (5因子+过热过滤)
│   ├── signal_generator.py        # 三层信号编排 + 分层调仓
│   ├── risk_control.py            # 多层风控 (止损/回撤/利润保护)
│   └── portfolio_manager.py       # 组合管理 (权重→交易指令)
├── backtest/                       # 回测引擎
│   ├── backtest_engine.py         # 主引擎 (时间推进+数据喂入)
│   ├── performance.py             # 绩效分析 (Sharpe/MDD/胜率/盈亏比)
│   ├── trade_logger.py            # 交易/仓位/信号记录
│   └── report_generator.py        # 图表 (6张) + HTML报告
├── main.py                         # 程序入口
├── requirements.txt                # 依赖
└── 资金驱动ETF轮动策略交易系统_PRD.md  # 产品需求文档
```

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/sambazhu/ETF-Rotation.git
cd ETF-Rotation

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行Mock回测（无需外部数据）
python main.py --mock

# 4. 运行真实数据回测 (AKShare, 免费)
python main.py --start 2023-01-01 --end 2025-12-31

# 5. 使用 Tushare Pro 数据源（推荐）
# 方式一：使用本地配置（推荐）
# 在项目根目录创建 .env 文件，写入：TUSHARE_TOKEN=your_token
python main.py --source tushare --start 2023-01-01 --end 2025-12-31

# 方式二：命令行参数
python main.py --source tushare --tushare-token YOUR_TOKEN --start 2023-01-01 --end 2025-12-31

# 6. 自定义资金
python main.py --mock --capital 1000000
```

## 回测输出

运行后自动生成 `output/` 目录:

| 文件 | 说明 |
|------|------|
| `backtest_report.html` | **完整HTML报告** (浏览器打开) |
| `nav_curve.png` | 策略净值 vs 基准曲线 |
| `drawdown.png` | 回撤曲线 |
| `positions.png` | 宽基/行业/现金仓位分布 |
| `monthly_returns.png` | 月度收益柱状图 |
| `macro_signals.png` | 宏观评分与仓位比例 |
| `trade_stats.png` | 交易分布统计 |
| `trades.csv` | 全部交易明细 |
| `nav.csv` | 每日净值序列 |
| `signals.csv` | 每日信号记录 |

## 核心指标

| 层级 | 因子 | 权重 |
|------|------|------|
| 宏观 | 全市场净流入·流入加速度·场内溢价·市场溢价·宽基动量 | 35/15/10/20/20% |
| 宽基 | 资金流强度(MFI)·流入加速(MFA)·折溢价偏离(PDI)·多周期动量(CMC) | 40/15/25/20% |
| 行业 | 资金流强度·流入加速·场内溢价·相对动量·估值分位 | 40/15/10/25/10% |

## 风控机制

- **单标的止损**: 追踪止损8%回撤 + 硬止损10%亏损
- **组合回撤管理**: 5%预警 → 8%降至30%仓位 → 12%清仓+5日冷却
- **利润保护**: 盈利超15%后追踪8%回撤止盈

## 技术栈

- Python 3.10+
- pandas / numpy — 数据处理
- AKShare — 免费A股ETF数据
- matplotlib — 图表生成

## License

MIT
