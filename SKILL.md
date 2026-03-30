---
name: etf-option-backtest
description: "ETF 期权策略回测技能。使用真实期权数据、Black-76 定价、SVI 曲面校准，执行三阶段策略回测（探索 + 验证 + 对冲）。触发词：ETF 期权回测、期权策略回测、etf option backtest、创业板 ETF 期权"
---

# ETF 期权策略回测技能

## 功能概述

本技能提供完整的 ETF 期权策略回测能力，包括：

1. **真实数据获取** - 从 AKShare 获取 ETF 和期权历史数据
2. **Black-76 定价** - 每个检查点实时重定价（考虑时间衰减 + 标的变动）
3. **SVI 曲面校准** - 波动率曲面拟合与 IV 估算
4. **三阶段策略** - 探索（开盘）+ 验证（30 分钟）+ 对冲（获利保护）
5. **绩效分析** - 详细交易记录、每日汇总、月度统计

## 触发条件

当用户提到以下任一关键词时触发：
- ETF 期权回测
- 期权策略回测
- etf option backtest
- 创业板 ETF 期权
- 期权定价分析
- SVI 波动率曲面

## 核心脚本

### 1. 数据获取 (`scripts/data_fetcher.py`)

```bash
python scripts/data_fetcher.py --etf 159915 --start 20260101 --end 20260331
```

**功能**:
- 获取 ETF 历史日线数据
- 获取期权合约列表（行权价、到期日）
- 获取期权历史行情（如有）

**输出**:
- `etf_{code}_{start}_{end}.csv` - ETF 历史数据
- `option_contracts_{code}.csv` - 期权合约信息

### 2. 期权定价 (`scripts/option_pricing.py`)

```bash
python scripts/option_pricing.py --etf-data etf_159915.csv --option-data option_contracts.csv
```

**功能**:
- Black-76 正向定价
- IV 逆向推导
- Greeks 计算 (Delta/Gamma/Theta/Vega/Rho)
- SVI 曲面校准

**输出**:
- `option_pricing_complete.csv` - 完整定价数据
- `option_iv_complete.csv` - IV 计算结果
- `svi_calibration_complete.csv` - SVI 参数

### 3. 策略回测 (`scripts/backtester.py`)

```bash
python scripts/backtester.py --etf-data etf_159915.csv --pricing option_pricing.csv --capital 200000
```

**策略逻辑**:

```
阶段 1: 探索阶段 (9:30 开盘)
  - 开盘涨 >0.5% → 买入平值 Call
  - 开盘跌 >0.5% → 买入平值 Put
  - 震荡 ±0.5% → 观望

阶段 2: 验证阶段 (每 30 分钟)
  - 价格持续同向 → 持有
  - 价格反向 >0.5% → 平仓反手

阶段 3: 对冲阶段 (获利保护)
  - 期权盈利 >20% → 卖出虚值期权 (Delta=0.3)
  - 每天最多对冲 1 次

风控：14:45 强制清仓 (当天合约不过夜)
```

**输出**:
- `daily_trades_detail.csv` - 逐笔交易明细
- `daily_summary.csv` - 每日汇总
- `backtest_report.md` - Markdown 报告

### 4. 绩效分析 (`scripts/analyzer.py`)

```bash
python scripts/analyzer.py --trades daily_trades_detail.csv --summary daily_summary.csv
```

**功能**:
- 计算绩效指标（收益率、夏普、最大回撤）
- 生成可视化图表
- 对比基准（Buy & Hold）

## 使用示例

### 示例 1: 完整回测流程

```bash
# 1. 获取数据
python scripts/data_fetcher.py --etf 159915 --start 20260101 --end 20260331

# 2. 期权定价 + SVI 校准
python scripts/option_pricing.py --etf-data temp/etf_159915_20260101_20260331.csv \
                                 --option-data temp/option_contracts_159915.csv

# 3. 执行回测
python scripts/backtester.py --etf-data temp/etf_159915_20260101_20260331.csv \
                             --pricing temp/option_pricing_complete.csv \
                             --capital 200000

# 4. 生成报告
python scripts/analyzer.py --trades reports/daily_trades_detail.csv \
                           --summary reports/daily_summary.csv
```

### 示例 2: 快速回测（使用估算价格）

```bash
python scripts/quick_backtest.py --etf 159915 --start 20260101 --end 20260331 \
                                  --capital 200000 --output reports/
```

## 关键参数

### 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `OPEN_THRESHOLD` | 0.005 | 开盘开仓阈值 (±0.5%) |
| `REVERSE_THRESHOLD` | 0.005 | 反手阈值 (0.5%) |
| `PROFIT_THRESHOLD` | 0.20 | 获利对冲阈值 (20%) |
| `OTM_DELTA` | 0.3 | 虚值期权 Delta (0.3) |
| `CHECK_INTERVAL` | 30 | 检查间隔 (分钟) |
| `CLEAR_TIME` | "14:45" | 强制清仓时间 |

### 定价参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `RISK_FREE_RATE` | 0.025 | 无风险利率 (2.5%) |
| `OPTION_MULTIPLIER` | 10000 | 期权合约乘数 |
| `COMMISSION_PER_CONTRACT` | 5.0 | 交易费用 (元/张) |

## 输出文件结构

```
reports/
├── daily_trades_detail.csv    # 逐笔交易明细
│   ├── date, time, action, option_code, strike, premium, pnl, reason
├── daily_summary.csv          # 每日汇总
│   ├── date, open, close, action, trades, pnl, return_pct, capital
├── backtest_report.md         # Markdown 报告
├── backtest_report.html       # HTML 可视化报告 (可选)
└── charts/
    ├── equity_curve.png       # 资金曲线
    ├── drawdown.png           # 回撤曲线
    └── monthly_returns.png    # 月度收益
```

## 注意事项

### 数据要求

1. **ETF 数据**: 必须包含 `date, open, high, low, close, volume`
2. **期权数据**: 必须包含 `code, type, strike, expiry_date, market_price`
3. **日期格式**: YYYY-MM-DD 或 YYYYMMDD

### 定价模型限制

1. **Black-76**: 适用于欧式期权，假设标的服从对数正态分布
2. **IV 估算**: 如无真实市场价格，使用 HV + 3% 估算
3. **SVI 校准**: 需要至少 5 个不同行权价的数据点

### 回测假设

1. **流动性**: 假设所有期权合约都能以理论价格成交
2. **交易费用**: 固定 5 元/张，未考虑印花税等
3. **滑点**: 未考虑市场冲击成本
4. **分红**: 未考虑 ETF 分红对期权价格的影响

## 常见问题

### Q1: 为什么回测结果与实盘差异大？

**可能原因**:
1. 使用了简化定价模型，未用真实期权价格
2. 反手频率设置不正确（应每 30 分钟检查）
3. 未考虑时间衰减（应固定到期日，不是每月重置）
4. IV 估算不准确（应用真实 IV 曲面）

**解决方案**: 使用 `data_fetcher.py` 获取真实期权历史数据

### Q2: 如何调整策略参数？

编辑 `scripts/backtester.py` 中的配置部分：

```python
OPEN_THRESHOLD = 0.005      # 调整为 0.01 表示±1%
REVERSE_THRESHOLD = 0.005   # 调整为 0.01 表示 1% 反向
PROFIT_THRESHOLD = 0.20     # 调整为 0.30 表示 30% 获利对冲
```

### Q3: 如何回测其他 ETF？

修改 `--etf` 参数：

```bash
python scripts/data_fetcher.py --etf 510300  # 沪深 300ETF
python scripts/data_fetcher.py --etf 510050  # 上证 50ETF
```

## 依赖安装

```bash
pip install akshare pandas numpy py_vollib scipy matplotlib
```

## 注意事项

1. **网络连接**: AKShare 需要访问东方财富 API，请确保网络畅通
2. **数据延迟**: 实时数据可能有 15 分钟延迟
3. **API 限制**: 频繁调用可能触发限流，建议添加延时

## 故障排除

### 问题 1: 连接错误

```
requests.exceptions.ConnectionError
```

**解决**: 检查网络连接，或改用本地缓存数据

### 问题 2: 数据为空

**解决**: 检查日期范围是否为交易日，ETF 代码是否正确

### 问题 3: 定价异常

**解决**: 检查 IV 估算是否合理，确保 days_to_expiry > 0

## 版本历史

- **v1.0** (2026-03-30): 初始版本，包含完整回测流程
- **v1.1** (2026-03-30): 修正 Black-76 实时定价逻辑
- **v1.2** (2026-03-30): 添加 SVI 曲面校准功能

## 参考资料

- [AKShare 文档](https://akshare.akfamily.xyz/)
- [py_vollib 文档](https://github.com/letianzj/py_vollib)
- [SVI 模型论文](https://arxiv.org/abs/1204.0646)
