#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速回测脚本 - 一键执行完整回测流程
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime
from py_vollib.black import black
import argparse
import os

RISK_FREE_RATE = 0.025
OPTION_MULTIPLIER = 10000
COMMISSION = 5.0


def quick_backtest(etf_code: str, start_date: str, end_date: str, 
                   initial_capital: float = 200000, output_dir: str = "reports"):
    """
    快速回测 - 使用 Black-76 估算价格
    
    Args:
        etf_code: ETF 代码
        start_date: 开始日期 YYYYMMDD
        end_date: 结束日期 YYYYMMDD
        initial_capital: 初始资金
        output_dir: 输出目录
    """
    print("=" * 70)
    print(f"ETF 期权策略快速回测 - {etf_code}")
    print("=" * 70)
    
    # 1. 获取 ETF 数据
    print(f"\n1. 获取 ETF {etf_code} 数据...")
    etf_data = ak.fund_etf_hist_em(
        symbol=etf_code,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust=""
    )
    etf_data['date'] = pd.to_datetime(etf_data['日期'])
    # 重命名列
    etf_data = etf_data.rename(columns={
        '开盘': 'open', '收盘': 'close', '最高': 'high', '最低': 'low', '成交量': 'volume'
    })
    etf_data = etf_data.sort_values('date').reset_index(drop=True)
    print(f"   ✓ {len(etf_data)} 个交易日")
    
    # 2. 执行回测
    print("\n2. 执行回测...")
    
    current_capital = initial_capital
    daily_results = []
    all_trades = []
    
    for idx in range(1, len(etf_data)):
        row = etf_data.iloc[idx]
        prev_row = etf_data.iloc[idx - 1]
        
        date = row['date'].strftime('%Y-%m-%d')
        prev_close = prev_row['close']
        open_price = row['open']
        close_price = row['close']
        
        capital_before = current_capital
        day_pnl = 0.0
        day_trades = []
        action = '观望'
        positions = {}
        
        # 开盘信号
        open_return = (open_price - prev_close) / prev_close
        
        if open_return > 0.005:
            signal = 'call'
            action = '看涨'
        elif open_return < -0.005:
            signal = 'put'
            action = '看跌'
        else:
            signal = None
        
        if signal:
            # 估算波动率和到期时间
            if idx >= 20:
                returns = etf_data.iloc[idx-20:idx]['close'].pct_change().dropna()
                hist_vol = returns.std() * np.sqrt(252)
            else:
                hist_vol = 0.25
            
            implied_vol = hist_vol + 0.03
            days_to_expiry = 30
            time_to_expiry = days_to_expiry / 365.0
            strike = round(open_price, 2)
            
            # Black-76 定价
            premium = black(
                flag='c' if signal == 'call' else 'p',
                F=open_price, K=strike, t=time_to_expiry,
                r=RISK_FREE_RATE, sigma=implied_vol
            )
            
            positions[signal] = {
                'type': signal, 'strike': strike,
                'open_price': premium, 'open_iv': implied_vol
            }
            
            day_trades.append({
                'date': date, 'time': '09:30', 'action': '买入开仓',
                'option': f"{signal}_{date}", 'strike': strike,
                'premium': round(premium, 4), 'quantity': 1,
                'commission': COMMISSION, 'pnl': 0.0, 'reason': f'开盘{action}'
            })
            
            current_capital -= COMMISSION
            print(f"{date} 开盘{open_return*100:+.2f}% → {action} @{premium:.4f}")
        else:
            print(f"{date} 开盘{open_return*100:+.2f}% → 观望")
        
        # 反手检查
        if positions:
            check_return = (close_price - open_price) / open_price
            existing_signal = list(positions.values())[0]['type']
            
            reverse_signal = None
            if existing_signal == 'call' and check_return < -0.005:
                reverse_signal = 'put'
            elif existing_signal == 'put' and check_return > 0.005:
                reverse_signal = 'call'
            
            if reverse_signal:
                pos = positions[existing_signal]
                days_to_expiry = 30
                time_to_expiry = days_to_expiry / 365.0
                
                close_premium = black(
                    flag='c' if reverse_signal == 'call' else 'p',
                    F=close_price, K=pos['strike'], t=time_to_expiry,
                    r=RISK_FREE_RATE, sigma=pos['open_iv']
                )
                
                if pos['type'] == 'call':
                    pnl = (close_premium - pos['open_price']) * OPTION_MULTIPLIER
                else:
                    pnl = (pos['open_price'] - close_premium) * OPTION_MULTIPLIER
                
                pnl -= COMMISSION
                day_pnl += pnl
                
                day_trades.append({
                    'date': date, 'time': '14:00', 'action': '卖出平仓',
                    'option': f"{pos['type']}_{date}", 'strike': pos['strike'],
                    'premium': round(close_premium, 4), 'quantity': 1,
                    'commission': COMMISSION, 'pnl': pnl, 'reason': '反手平仓'
                })
                
                current_capital += pnl
                positions = {}
                print(f"  反手平仓：¥{pnl:+.2f}")
                
                # 开新仓
                premium = black(
                    flag='c' if reverse_signal == 'call' else 'p',
                    F=close_price, K=round(close_price, 2), t=time_to_expiry,
                    r=RISK_FREE_RATE, sigma=pos['open_iv']
                )
                
                positions[reverse_signal] = {
                    'type': reverse_signal, 'strike': round(close_price, 2),
                    'open_price': premium, 'open_iv': pos['open_iv']
                }
                
                day_trades.append({
                    'date': date, 'time': '14:00', 'action': '买入开仓',
                    'option': f"{reverse_signal}_{date}_rev", 'strike': round(close_price, 2),
                    'premium': round(premium, 4), 'quantity': 1,
                    'commission': COMMISSION, 'pnl': 0.0, 'reason': '反手开仓'
                })
                
                current_capital -= COMMISSION
                print(f"  反手开仓：{reverse_signal} @{premium:.4f}")
        
        # 阶段 3: 对冲检查 (获利>5% 触发)
        if positions and True:  # 简化：每天允许对冲
            for pos_type, pos in list(positions.items()):
                days_to_expiry = 30
                time_to_expiry = days_to_expiry / 365.0
                
                current_premium = black(
                    flag='c' if pos_type == 'call' else 'p',
                    F=close_price, K=pos['strike'], t=time_to_expiry,
                    r=RISK_FREE_RATE, sigma=pos['open_iv']
                )
                
                # 计算盈利比例
                if pos_type == 'call':
                    pnl_ratio = (current_premium - pos['open_price']) / pos['open_price']
                else:
                    pnl_ratio = (pos['open_price'] - current_premium) / pos['open_price']
                
                # 获利>5% 触发对冲
                if pnl_ratio > 0.05:
                    hedge_strike = round(close_price * 1.05, 2) if pos_type == 'call' else round(close_price * 0.95, 2)
                    hedge_premium = black(
                        flag='c' if pos_type == 'call' else 'p',
                        F=close_price, K=hedge_strike, t=time_to_expiry,
                        r=RISK_FREE_RATE, sigma=pos['open_iv'] * 0.8
                    )
                    
                    day_trades.append({
                        'date': date, 'time': '14:30', 'action': '卖出开仓',
                        'option': f"hedge_{pos_type}_{date}", 'strike': hedge_strike,
                        'premium': round(hedge_premium, 4), 'quantity': 1,
                        'commission': COMMISSION, 'pnl': 0.0, 'reason': '获利对冲 (>5%)'
                    })
                    
                    current_capital += hedge_premium * OPTION_MULTIPLIER - COMMISSION
                    print(f"  获利对冲：{pos_type} 盈利{pnl_ratio*100:.1f}% > 5% → 卖出虚值{hedge_strike}")
                    break
        
        # 14:45 清仓
        if positions:
            for pos_type, pos in positions.items():
                days_to_expiry = 30
                time_to_expiry = days_to_expiry / 365.0
                
                close_premium = black(
                    flag='c' if pos_type == 'call' else 'p',
                    F=close_price, K=pos['strike'], t=time_to_expiry,
                    r=RISK_FREE_RATE, sigma=pos['open_iv']
                )
                
                if pos_type == 'call':
                    pnl = (close_premium - pos['open_price']) * OPTION_MULTIPLIER
                else:
                    pnl = (pos['open_price'] - close_premium) * OPTION_MULTIPLIER
                
                pnl -= COMMISSION
                day_pnl += pnl
                
                day_trades.append({
                    'date': date, 'time': '14:45', 'action': '卖出平仓',
                    'option': f"{pos_type}_{date}", 'strike': pos['strike'],
                    'premium': round(close_premium, 4), 'quantity': 1,
                    'commission': COMMISSION, 'pnl': pnl, 'reason': '日终清仓'
                })
                
                current_capital += pnl
                print(f"  日终清仓：¥{pnl:+.2f}")
        
        # 记录结果
        daily_return = day_pnl / capital_before * 100
        daily_results.append({
            'date': date, 'open': open_price, 'close': close_price,
            'open_return': open_return * 100, 'action': action,
            'trades': len(day_trades), 'pnl': day_pnl,
            'return_pct': daily_return, 'capital': current_capital
        })
        all_trades.extend(day_trades)
    
    # 3. 保存结果
    print("\n3. 保存结果...")
    os.makedirs(output_dir, exist_ok=True)
    
    daily_df = pd.DataFrame(daily_results)
    trades_df = pd.DataFrame(all_trades)
    
    daily_df.to_csv(f"{output_dir}/daily_summary.csv", index=False, encoding='utf-8-sig')
    trades_df.to_csv(f"{output_dir}/daily_trades_detail.csv", index=False, encoding='utf-8-sig')
    
    # 4. 打印汇总
    print("\n" + "=" * 70)
    print("回测结果汇总")
    print("=" * 70)
    
    total_pnl = daily_df['pnl'].sum()
    total_return = (daily_df['capital'].iloc[-1] / initial_capital - 1) * 100
    winning_days = len(daily_df[daily_df['pnl'] > 0])
    losing_days = len(daily_df[daily_df['pnl'] < 0])
    
    print(f"""
初始资金：¥{initial_capital:,.2f}
期末资金：¥{daily_df['capital'].iloc[-1]:,.2f}
总盈亏：¥{total_pnl:+,.2f}
总收益率：{total_return:+.2f}%

交易日：{len(daily_df)} 天
交易天数：{len(daily_df[daily_df['action'] != '观望'])} 天
空仓天数：{len(daily_df[daily_df['action'] == '观望'])} 天
盈利天数：{winning_days} 天
亏损天数：{losing_days} 天
胜率：{winning_days/(winning_days+losing_days)*100:.1f}%

最大单日盈利：¥{daily_df['pnl'].max():,.2f}
最大单日亏损：¥{daily_df['pnl'].min():,.2f}
交易笔数：{len(trades_df)} 笔

结果已保存至：{output_dir}/
""")
    
    return daily_df, trades_df


def main():
    parser = argparse.ArgumentParser(description="ETF 期权策略快速回测")
    parser.add_argument("--etf", type=str, default="159915", help="ETF 代码")
    parser.add_argument("--start", type=str, required=True, help="开始日期 YYYYMMDD")
    parser.add_argument("--end", type=str, required=True, help="结束日期 YYYYMMDD")
    parser.add_argument("--capital", type=float, default=200000, help="初始资金")
    parser.add_argument("--output", type=str, default="reports", help="输出目录")
    
    args = parser.parse_args()
    
    quick_backtest(args.etf, args.start, args.end, args.capital, args.output)


if __name__ == "__main__":
    main()
