#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 期权策略回测引擎
实现三阶段策略：探索 + 验证 + 对冲
"""

import pandas as pd
import numpy as np
from datetime import datetime
from py_vollib.black import black
import argparse
import os

RISK_FREE_RATE = 0.025
OPTION_MULTIPLIER = 10000
COMMISSION_PER_CONTRACT = 5.0


class ETFOptionBacktester:
    """ETF 期权策略回测引擎"""
    
    def __init__(self, initial_capital=200000):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        
        # 策略参数
        self.open_threshold = 0.005  # 开盘开仓阈值±0.5%
        self.reverse_threshold = 0.005  # 反手阈值 0.5%
        self.profit_threshold = 0.20  # 获利对冲阈值 20%
        self.check_interval = 30  # 检查间隔 (分钟)
        self.clear_time = "14:45"  # 强制清仓时间
        
        # 持仓管理
        self.positions = {}
        self.hedge_count_today = 0
        self.max_hedge_per_day = 1
        
        # 结果记录
        self.daily_results = []
        self.all_trades = []
    
    def black76_price(self, F, K, t, sigma, option_type='call'):
        """Black-76 定价"""
        try:
            return black(
                flag='c' if option_type == 'call' else 'p',
                F=F, K=K, t=t, r=RISK_FREE_RATE, sigma=sigma
            )
        except:
            return 0.0001
    
    def estimate_volatility(self, etf_data, date_idx):
        """估算隐含波动率 (HV + 溢价)"""
        if date_idx >= 20:
            returns = etf_data.iloc[date_idx-20:date_idx]['close'].pct_change().dropna()
            hist_vol = returns.std() * np.sqrt(252)
            return hist_vol + 0.03
        return 0.28
    
    def get_expiry_days(self, trade_date, fixed_expiry_date=None):
        """计算到期天数"""
        if fixed_expiry_date:
            expiry = pd.to_datetime(fixed_expiry_date)
        else:
            # 简化：假设 30 天
            return 30
        
        days = (expiry - pd.to_datetime(trade_date)).days
        return max(days, 1)
    
    def run_backtest(self, etf_data, pricing_data=None, fixed_expiry=None):
        """
        执行回测
        
        Args:
            etf_data: ETF 日线数据
            pricing_data: 期权定价数据 (可选，如 None 则使用 Black-76 估算)
            fixed_expiry: 固定到期日 (如'2026-04-24')
        """
        print("\n开始回测...")
        print("=" * 70)
        
        for idx in range(1, len(etf_data)):
            row = etf_data.iloc[idx]
            prev_row = etf_data.iloc[idx - 1]
            
            date = row['date'] if isinstance(row['date'], str) else row['date'].strftime('%Y-%m-%d')
            prev_close = prev_row['close']
            open_price = row['open']
            close_price = row['close']
            
            # 每日重置
            capital_before = self.current_capital
            self.positions = {}
            self.hedge_count_today = 0
            day_pnl = 0.0
            day_trades = []
            action = '观望'
            
            # ========== 阶段 1: 开盘信号 (9:30) ==========
            open_return = (open_price - prev_close) / prev_close
            
            if open_return > self.open_threshold:
                signal = 'call'
                action = '看涨'
            elif open_return < -self.open_threshold:
                signal = 'put'
                action = '看跌'
            else:
                signal = None
            
            if signal:
                # 获取波动率
                implied_vol = self.estimate_volatility(etf_data, idx)
                days_to_expiry = self.get_expiry_days(date, fixed_expiry)
                time_to_expiry = days_to_expiry / 365.0
                
                # 平值期权
                strike = round(open_price, 2)
                
                # Black-76 定价
                premium = self.black76_price(open_price, strike, time_to_expiry, implied_vol, signal)
                
                # 开仓
                self.positions[signal] = {
                    'type': signal,
                    'strike': strike,
                    'open_price': premium,
                    'open_iv': implied_vol,
                    'days': days_to_expiry
                }
                
                day_trades.append({
                    'date': date,
                    'time': '09:30',
                    'action': '买入开仓',
                    'option': f"{signal}_{date}",
                    'strike': strike,
                    'premium': round(premium, 4),
                    'quantity': 1,
                    'commission': COMMISSION_PER_CONTRACT,
                    'pnl': 0.0,
                    'reason': f'开盘{action}'
                })
                
                self.current_capital -= COMMISSION_PER_CONTRACT
                print(f"{date} 开盘{open_return*100:+.2f}% → {action} @{premium:.4f}")
            else:
                print(f"{date} 开盘{open_return*100:+.2f}% → 观望")
            
            # ========== 阶段 2: 反手检查 (简化：14:00 检查一次) ==========
            if self.positions:
                check_return = (close_price - open_price) / open_price
                existing_signal = list(self.positions.values())[0]['type']
                
                reverse_signal = None
                if existing_signal == 'call' and check_return < -self.reverse_threshold:
                    reverse_signal = 'put'
                elif existing_signal == 'put' and check_return > self.reverse_threshold:
                    reverse_signal = 'call'
                
                if reverse_signal:
                    # 平仓
                    pos = self.positions[existing_signal]
                    days_to_expiry = self.get_expiry_days(date, fixed_expiry)
                    time_to_expiry = days_to_expiry / 365.0
                    
                    close_premium = self.black76_price(
                        close_price, pos['strike'], time_to_expiry, pos['open_iv'], reverse_signal
                    )
                    
                    # 计算盈亏
                    if pos['type'] == 'call':
                        pnl = (close_premium - pos['open_price']) * OPTION_MULTIPLIER
                    else:
                        pnl = (pos['open_price'] - close_premium) * OPTION_MULTIPLIER
                    
                    pnl -= COMMISSION_PER_CONTRACT
                    day_pnl += pnl
                    
                    day_trades.append({
                        'date': date,
                        'time': '14:00',
                        'action': '卖出平仓',
                        'option': f"{pos['type']}_{date}",
                        'strike': pos['strike'],
                        'premium': round(close_premium, 4),
                        'quantity': 1,
                        'commission': COMMISSION_PER_CONTRACT,
                        'pnl': pnl,
                        'reason': '反手平仓'
                    })
                    
                    self.current_capital += pnl
                    self.positions = {}
                    print(f"  反手平仓：¥{pnl:+.2f}")
                    
                    # 开新仓
                    days_to_expiry = self.get_expiry_days(date, fixed_expiry)
                    time_to_expiry = days_to_expiry / 365.0
                    strike = round(close_price, 2)
                    
                    premium = self.black76_price(close_price, strike, time_to_expiry, pos['open_iv'], reverse_signal)
                    
                    self.positions[reverse_signal] = {
                        'type': reverse_signal,
                        'strike': strike,
                        'open_price': premium,
                        'open_iv': pos['open_iv'],
                        'days': days_to_expiry
                    }
                    
                    day_trades.append({
                        'date': date,
                        'time': '14:00',
                        'action': '买入开仓',
                        'option': f"{reverse_signal}_{date}_rev",
                        'strike': strike,
                        'premium': round(premium, 4),
                        'quantity': 1,
                        'commission': COMMISSION_PER_CONTRACT,
                        'pnl': 0.0,
                        'reason': '反手开仓'
                    })
                    
                    self.current_capital -= COMMISSION_PER_CONTRACT
                    print(f"  反手开仓：{reverse_signal} @{premium:.4f}")
            
            # ========== 14:45 清仓 ==========
            if self.positions:
                for pos_type, pos in list(self.positions.items()):
                    days_to_expiry = self.get_expiry_days(date, fixed_expiry)
                    time_to_expiry = days_to_expiry / 365.0
                    
                    close_premium = self.black76_price(
                        close_price, pos['strike'], time_to_expiry, pos['open_iv'], pos_type
                    )
                    
                    # 计算盈亏
                    if pos_type == 'call':
                        pnl = (close_premium - pos['open_price']) * OPTION_MULTIPLIER
                    else:
                        pnl = (pos['open_price'] - close_premium) * OPTION_MULTIPLIER
                    
                    pnl -= COMMISSION_PER_CONTRACT
                    day_pnl += pnl
                    
                    day_trades.append({
                        'date': date,
                        'time': '14:45',
                        'action': '卖出平仓',
                        'option': f"{pos_type}_{date}",
                        'strike': pos['strike'],
                        'premium': round(close_premium, 4),
                        'quantity': 1,
                        'commission': COMMISSION_PER_CONTRACT,
                        'pnl': pnl,
                        'reason': '日终清仓'
                    })
                    
                    self.current_capital += pnl
                    print(f"  日终清仓：¥{pnl:+.2f}")
                
                self.positions = {}
            
            # 记录结果
            daily_return = day_pnl / capital_before * 100
            self.daily_results.append({
                'date': date,
                'open': open_price,
                'close': close_price,
                'open_return': open_return * 100,
                'action': action,
                'trades': len(day_trades),
                'pnl': day_pnl,
                'return_pct': daily_return,
                'capital': self.current_capital
            })
            self.all_trades.extend(day_trades)
        
        print(f"\n回测完成：{len(self.daily_results)} 个交易日，{len(self.all_trades)} 笔交易")
        return pd.DataFrame(self.daily_results), pd.DataFrame(self.all_trades)


def run_backtest(etf_data_path: str, pricing_data_path: str = None, 
                 initial_capital: float = 200000, output_dir: str = "reports",
                 fixed_expiry: str = None):
    """执行回测"""
    
    # 加载数据
    print("加载 ETF 数据...")
    etf_data = pd.read_csv(etf_data_path)
    etf_data['date'] = pd.to_datetime(etf_data['date'])
    etf_data = etf_data.sort_values('date').reset_index(drop=True)
    
    pricing_data = None
    if pricing_data_path and os.path.exists(pricing_data_path):
        pricing_data = pd.read_csv(pricing_data_path)
        print(f"加载定价数据：{len(pricing_data)} 条")
    
    # 创建回测引擎
    backtester = ETFOptionBacktester(initial_capital)
    
    # 执行回测
    daily_results, all_trades = backtester.run_backtest(etf_data, pricing_data, fixed_expiry)
    
    # 保存结果
    os.makedirs(output_dir, exist_ok=True)
    daily_results.to_csv(f"{output_dir}/daily_summary.csv", index=False, encoding='utf-8-sig')
    all_trades.to_csv(f"{output_dir}/daily_trades_detail.csv", index=False, encoding='utf-8-sig')
    
    # 打印汇总
    print("\n" + "=" * 70)
    print("回测结果汇总")
    print("=" * 70)
    
    total_pnl = daily_results['pnl'].sum()
    total_return = (daily_results['capital'].iloc[-1] / initial_capital - 1) * 100
    winning_days = len(daily_results[daily_results['pnl'] > 0])
    losing_days = len(daily_results[daily_results['pnl'] < 0])
    
    print(f"""
初始资金：¥{initial_capital:,.2f}
期末资金：¥{daily_results['capital'].iloc[-1]:,.2f}
总盈亏：¥{total_pnl:+,.2f}
总收益率：{total_return:+.2f}%

交易日：{len(daily_results)} 天
交易天数：{len(daily_results[daily_results['action'] != '观望'])} 天
空仓天数：{len(daily_results[daily_results['action'] == '观望'])} 天
盈利天数：{winning_days} 天
亏损天数：{losing_days} 天
胜率：{winning_days/(winning_days+losing_days)*100:.1f}%

最大单日盈利：¥{daily_results['pnl'].max():,.2f}
最大单日亏损：¥{daily_results['pnl'].min():,.2f}
交易笔数：{len(all_trades)} 笔

结果已保存至：{output_dir}/
""")
    
    return daily_results, all_trades


def main():
    parser = argparse.ArgumentParser(description="ETF 期权策略回测")
    parser.add_argument("--etf-data", type=str, required=True, help="ETF 数据文件路径")
    parser.add_argument("--pricing", type=str, default=None, help="期权定价数据文件路径 (可选)")
    parser.add_argument("--capital", type=float, default=200000, help="初始资金")
    parser.add_argument("--output", type=str, default="reports", help="输出目录")
    parser.add_argument("--expiry", type=str, default=None, help="固定到期日 (如 2026-04-24)")
    
    args = parser.parse_args()
    
    run_backtest(args.etf_data, args.pricing, args.capital, args.output, args.expiry)


if __name__ == "__main__":
    main()
