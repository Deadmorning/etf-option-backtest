#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 期权数据获取模块
从 AKShare 获取 ETF 和期权历史数据
"""

import akshare as ak
import pandas as pd
from datetime import datetime
import argparse
import os


def fetch_etf_data(etf_code: str, start_date: str, end_date: str, output_dir: str = "temp"):
    """
    获取 ETF 历史日线数据
    
    Args:
        etf_code: ETF 代码 (如 159915)
        start_date: 开始日期 YYYYMMDD
        end_date: 结束日期 YYYYMMDD
        output_dir: 输出目录
    
    Returns:
        DataFrame with columns: date, open, high, low, close, volume
    """
    print(f"获取 ETF {etf_code} 日线数据：{start_date} - {end_date}")
    
    try:
        df = ak.fund_etf_hist_em(
            symbol=etf_code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust=""
        )
        
        # 重命名列
        df = df.rename(columns={
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "turnover"
        })
        
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        
        # 保存数据
        os.makedirs(output_dir, exist_ok=True)
        output_file = f"{output_dir}/etf_{etf_code}_{start_date}_{end_date}.csv"
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        
        print(f"✓ 获取到 {len(df)} 条 ETF 数据")
        print(f"✓ 数据已保存至：{output_file}")
        
        return df
        
    except Exception as e:
        print(f"✗ 获取 ETF 数据失败：{e}")
        return pd.DataFrame()


def fetch_option_contracts(etf_code: str, output_dir: str = "temp"):
    """
    获取 ETF 期权合约列表
    
    Args:
        etf_code: ETF 代码 (如 159915)
        output_dir: 输出目录
    
    Returns:
        DataFrame with columns: code, type, strike, expiry_date, etc.
    """
    print(f"获取 ETF {etf_code} 期权合约列表")
    
    try:
        # 获取深交所期权数据
        option_data = ak.option_current_day_szse()
        
        if option_data is not None and len(option_data) > 0:
            # 筛选该 ETF 的期权
            etf_options = option_data[
                option_data.apply(
                    lambda x: x.astype(str).str.contains(etf_code, case=False).any(), 
                    axis=1
                )
            ]
            
            if len(etf_options) > 0:
                os.makedirs(output_dir, exist_ok=True)
                output_file = f"{output_dir}/option_contracts_{etf_code}.csv"
                etf_options.to_csv(output_file, index=False, encoding='utf-8-sig')
                
                print(f"✓ 获取到 {len(etf_options)} 条期权合约")
                print(f"✓ 数据已保存至：{output_file}")
                
                return etf_options
            else:
                print(f"⚠ 未找到 ETF {etf_code} 的期权合约")
                return pd.DataFrame()
        else:
            print("⚠ 未获取到期权数据")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"✗ 获取期权合约失败：{e}")
        return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(description="获取 ETF 和期权历史数据")
    parser.add_argument("--etf", type=str, default="159915", help="ETF 代码")
    parser.add_argument("--start", type=str, required=True, help="开始日期 YYYYMMDD")
    parser.add_argument("--end", type=str, required=True, help="结束日期 YYYYMMDD")
    parser.add_argument("--output", type=str, default="temp", help="输出目录")
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("ETF 期权数据获取工具")
    print("=" * 70)
    
    # 获取 ETF 数据
    etf_data = fetch_etf_data(args.etf, args.start, args.end, args.output)
    
    # 获取期权合约
    option_data = fetch_option_contracts(args.etf, args.output)
    
    print("\n" + "=" * 70)
    print("数据获取完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
