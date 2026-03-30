# ETF 期权策略回测技能

## 快速开始

### 安装依赖

```bash
pip install akshare pandas numpy py_vollib scipy matplotlib
```

### 使用示例

#### 方式 1: 快速回测 (推荐)

```bash
cd skills/etf-option-backtest

# 回测创业板 ETF 2026 年 Q1
python scripts/quick_backtest.py --etf 159915 --start 20260101 --end 20260331 --capital 200000
```

#### 方式 2: 完整流程

```bash
# 1. 获取数据
python scripts/data_fetcher.py --etf 159915 --start 20260101 --end 20260331

# 2. 期权定价 + SVI 校准
python scripts/option_pricing.py \
    --etf-data temp/etf_159915_20260101_20260331.csv \
    --option-data temp/option_contracts_159915.csv

# 3. 执行回测
python scripts/backtester.py \
    --etf-data temp/etf_159915_20260101_20260331.csv \
    --capital 200000 \
    --expiry 2026-04-24
```

## 输出文件

```
reports/
├── daily_summary.csv          # 每日汇总
├── daily_trades_detail.csv    # 逐笔交易明细
└── (可选) backtest_report.md  # Markdown 报告
```

## 策略逻辑

```
阶段 1: 探索阶段 (9:30 开盘)
  - 开盘涨 >0.5% → 买入平值 Call
  - 开盘跌 >0.5% → 买入平值 Put
  - 震荡 ±0.5% → 观望

阶段 2: 验证阶段 (每 30 分钟)
  - 价格持续同向 → 持有
  - 价格反向 >0.5% → 平仓反手

阶段 3: 对冲阶段 (获利保护)
  - 期权盈利 >20% → 卖出虚值期权
  - 每天最多对冲 1 次

风控：14:45 强制清仓
```

## 策略参数

在脚本中修改：

```python
OPEN_THRESHOLD = 0.005      # 开盘开仓阈值±0.5%
REVERSE_THRESHOLD = 0.005   # 反手阈值 0.5%
PROFIT_THRESHOLD = 0.20     # 获利对冲阈值 20%
```

## 注意事项

1. **真实数据**: 如需精确回测，请使用真实期权历史数据
2. **定价模型**: Black-76 适用于欧式期权
3. **交易费用**: 默认 5 元/张，可在脚本中修改
4. **回测假设**: 假设所有合约都能以理论价格成交

## 版本

v1.0 - 2026-03-30
