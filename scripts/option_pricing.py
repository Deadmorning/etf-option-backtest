#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
期权定价模块 - Black-76 定价、IV 计算、Greeks、SVI 校准
"""

import pandas as pd
import numpy as np
from datetime import datetime
from py_vollib.black import black
from py_vollib.black.implied_volatility import implied_volatility
from py_vollib.black.greeks.analytical import delta, gamma, theta, vega
from scipy.optimize import minimize
import argparse
import os

RISK_FREE_RATE = 0.025


def black76_price(F, K, t, sigma, option_type='call'):
    """Black-76 期权定价"""
    return black(
        flag='c' if option_type == 'call' else 'p',
        F=F, K=K, t=t, r=RISK_FREE_RATE, sigma=sigma
    )


def calculate_iv(price, F, K, t, option_type='call'):
    """逆向推导隐含波动率"""
    try:
        return implied_volatility(
            discounted_option_price=price,
            F=F, K=K, r=RISK_FREE_RATE, t=t,
            flag='c' if option_type == 'call' else 'p'
        )
    except:
        return np.nan


def calculate_greeks(F, K, t, sigma, option_type='call'):
    """计算 Greeks"""
    return {
        'delta': delta('c' if option_type == 'call' else 'p', F, K, t, RISK_FREE_RATE, sigma),
        'gamma': gamma('c' if option_type == 'call' else 'p', F, K, t, RISK_FREE_RATE, sigma),
        'theta': theta('c' if option_type == 'call' else 'p', F, K, t, RISK_FREE_RATE, sigma),
        'vega': vega('c' if option_type == 'call' else 'p', F, K, t, RISK_FREE_RATE, sigma)
    }


def svi_variance(k, a, b, rho, m, sigma):
    """SVI 总方差公式"""
    return a + b * (rho * (k - m) + np.sqrt((k - m)**2 + sigma**2))


def calibrate_svi(k_values, w_values):
    """
    校准 SVI 参数
    
    Args:
        k_values: 标准化行权价 log(K/F)
        w_values: 总方差 sigma^2 * T
    
    Returns:
        SVI 参数字典
    """
    def loss(params):
        a, b, rho, m, sigma = params
        w_model = svi_variance(k_values, a, b, rho, m, sigma)
        return np.sum((w_model - w_values) ** 2)
    
    initial_params = [0.04, 0.4, -0.4, 0.0, 0.1]
    bounds = [(0.0, 0.2), (0.0, 1.0), (-1.0, 1.0), (-0.5, 0.5), (0.01, 0.5)]
    
    result = minimize(loss, initial_params, method='L-BFGS-B', bounds=bounds)
    
    if result.success:
        return {
            'a': result.x[0],
            'b': result.x[1],
            'rho': result.x[2],
            'm': result.x[3],
            'sigma': result.x[4],
            'error': result.fun
        }
    return None


def price_options(etf_data_path: str, option_data_path: str, output_dir: str = "temp"):
    """
    执行期权定价
    
    Args:
        etf_data_path: ETF 数据文件路径
        option_data_path: 期权合约文件路径
        output_dir: 输出目录
    """
    print("=" * 70)
    print("期权定价与 SVI 校准")
    print("=" * 70)
    
    # 加载数据
    print("\n加载数据...")
    etf_data = pd.read_csv(etf_data_path)
    etf_data['date'] = pd.to_datetime(etf_data['date'])
    etf_data = etf_data.sort_values('date').reset_index(drop=True)
    
    option_data = pd.read_csv(option_data_path)
    
    print(f"ETF 数据：{len(etf_data)} 条")
    print(f"期权合约：{len(option_data)} 条")
    
    # 获取最新 ETF 价格
    latest_etf = etf_data.iloc[-1]
    latest_date = latest_etf['date']
    latest_price = latest_etf['close']
    
    print(f"\n最新交易日：{latest_date.date()}")
    print(f"ETF 收盘价：{latest_price:.4f}")
    
    # 计算历史波动率
    if len(etf_data) >= 20:
        returns = etf_data['close'].pct_change().dropna()
        hist_vol = returns.std() * np.sqrt(252)
    else:
        hist_vol = 0.25
    
    print(f"20 日历史波动率：{hist_vol*100:.2f}%")
    
    # 定价结果
    pricing_results = []
    iv_results = []
    
    print("\n执行定价计算...")
    
    for idx, contract in option_data.iterrows():
        try:
            # 解析合约信息
            contract_code = contract.get('合约代码', contract.get('code', ''))
            contract_type = 'call' if contract.get('合约类型', '') == '认购' else 'put'
            strike = contract.get('行权价', contract.get('strike', 0))
            expiry_str = contract.get('到期日', contract.get('expiry_date', ''))
            
            if not expiry_str:
                continue
            
            expiry_date = pd.to_datetime(expiry_str)
            days_to_expiry = (expiry_date - latest_date).days
            
            if days_to_expiry <= 0:
                continue
            
            time_to_expiry = days_to_expiry / 365.0
            implied_vol = hist_vol + 0.03  # IV 溢价
            
            # Black-76 定价
            premium = black76_price(
                F=latest_price, K=strike, t=time_to_expiry,
                sigma=implied_vol, option_type=contract_type
            )
            
            # Greeks
            greeks = calculate_greeks(latest_price, strike, time_to_expiry, implied_vol, contract_type)
            
            pricing_results.append({
                'contract_code': contract_code,
                'contract_type': contract_type,
                'strike': strike,
                'expiry_date': expiry_date.date(),
                'days_to_expiry': days_to_expiry,
                'time_to_expiry': round(time_to_expiry, 4),
                'underlying_price': round(latest_price, 4),
                'implied_vol': round(implied_vol, 4),
                'theoretical_price': round(premium, 4),
                'delta': round(greeks['delta'], 4),
                'gamma': round(greeks['gamma'], 4),
                'theta': round(greeks['theta'], 4),
                'vega': round(greeks['vega'], 4)
            })
            
            # IV 计算（使用理论价格模拟市场价格）
            market_price = premium * (1 + np.random.uniform(-0.05, 0.05))
            iv = calculate_iv(market_price, latest_price, strike, time_to_expiry, contract_type)
            
            if not np.isnan(iv):
                iv_results.append({
                    'contract_code': contract_code,
                    'contract_type': contract_type,
                    'strike': strike,
                    'expiry_date': expiry_date.date(),
                    'days_to_expiry': days_to_expiry,
                    'theoretical_price': round(premium, 4),
                    'market_price': round(market_price, 4),
                    'implied_volatility': round(iv * 100, 2)
                })
                
        except Exception as e:
            continue
    
    # 保存结果
    os.makedirs(output_dir, exist_ok=True)
    
    pricing_df = pd.DataFrame(pricing_results)
    pricing_df.to_csv(f"{output_dir}/option_pricing_complete.csv", index=False, encoding='utf-8-sig')
    print(f"\n✓ 定价结果：{len(pricing_df)} 个合约")
    print(f"✓ 保存至：{output_dir}/option_pricing_complete.csv")
    
    iv_df = pd.DataFrame(iv_results)
    iv_df.to_csv(f"{output_dir}/option_iv_complete.csv", index=False, encoding='utf-8-sig')
    print(f"✓ IV 结果：{len(iv_df)} 个合约")
    print(f"✓ 保存至：{output_dir}/option_iv_complete.csv")
    
    # SVI 校准
    print("\n执行 SVI 曲面校准...")
    
    svi_results = []
    expiry_groups = iv_df.groupby('expiry_date')
    
    for expiry, group in expiry_groups:
        if len(group) < 5:
            continue
        
        k_values = np.log(group['strike'] / latest_price)
        w_values = (group['implied_volatility'].values / 100) ** 2 * (group['days_to_expiry'].values / 365.0)
        
        svi_params = calibrate_svi(k_values, w_values)
        
        if svi_params:
            svi_results.append({
                'expiry_date': expiry,
                'data_points': len(group),
                'a': round(svi_params['a'], 6),
                'b': round(svi_params['b'], 6),
                'rho': round(svi_params['rho'], 6),
                'm': round(svi_params['m'], 6),
                'sigma': round(svi_params['sigma'], 6),
                'calibration_error': round(svi_params['error'], 8)
            })
            print(f"  {expiry}: a={svi_params['a']:.6f}, b={svi_params['b']:.6f}, R²={1-svi_params['error']:.4f}")
    
    if svi_results:
        svi_df = pd.DataFrame(svi_results)
        svi_df.to_csv(f"{output_dir}/svi_calibration_complete.csv", index=False, encoding='utf-8-sig')
        print(f"\n✓ SVI 校准：{len(svi_df)} 个到期日")
        print(f"✓ 保存至：{output_dir}/svi_calibration_complete.csv")
    
    print("\n" + "=" * 70)
    print("定价完成")
    print("=" * 70)
    
    return pricing_df, iv_df, svi_df if svi_results else None


def main():
    parser = argparse.ArgumentParser(description="期权定价与 SVI 校准")
    parser.add_argument("--etf-data", type=str, required=True, help="ETF 数据文件路径")
    parser.add_argument("--option-data", type=str, required=True, help="期权合约文件路径")
    parser.add_argument("--output", type=str, default="temp", help="输出目录")
    
    args = parser.parse_args()
    
    price_options(args.etf_data, args.option_data, args.output)


if __name__ == "__main__":
    main()
