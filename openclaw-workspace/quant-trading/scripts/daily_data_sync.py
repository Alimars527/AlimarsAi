#!/usr/bin/env python3
"""
每日收盘后数据同步脚本（全市场批量版）

用法: python daily_data_sync.py [TRADE_DATE]
不传参数则自动拉今天的数据

核心逻辑：
- pro.daily(trade_date=) 可一次性拉全市场所有股票（~5500只）
- pro.daily_basic(trade_date=) 同理，一次性拉全市场财务数据
- pro.index_daily() 拉上证指数
- 数据写入 data/daily/ 和 data/daily_basic/ 下的分股票CSV
- 已有数据采用 dedup + merge 策略，不重复拉取
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import tushare as ts

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.config import load_settings


def get_trade_date():
    if len(sys.argv) >= 2:
        return sys.argv[1]
    today = datetime.now()
    return today.strftime('%Y%m%d')


def sync_market_daily(pro, trade_date: str, root: Path) -> dict:
    """
    全市场日线批量同步（核心高效路径）
    一次API调用返回所有股票当日数据
    """
    df = pro.daily(trade_date=trade_date)
    if df is None or df.empty:
        return {'status': 'no_data', 'rows': 0}

    df = df.sort_values('ts_code')
    total = len(df)
    print(f"  全市场日线：获取到 {total} 条记录")

    # 写入分股票CSV
    daily_dir = root / 'data' / 'daily'
    daily_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for ts_code in df['ts_code'].unique():
        code_df = df[df['ts_code'] == ts_code].copy()
        path = daily_dir / f'{ts_code}.csv'
        if path.exists():
            existing = pd.read_csv(path, dtype=str)
            merged = pd.concat([existing, code_df]).drop_duplicates(subset='trade_date', keep='last')
            merged = merged.sort_values('trade_date')
            merged.to_csv(path, index=False)
        else:
            code_df.to_csv(path, index=False)
        written += 1

    return {'status': 'ok', 'rows': total, 'files_written': written}


def sync_market_daily_basic(pro, trade_date: str, root: Path) -> dict:
    """
    全市场日线财务数据批量同步
    一次API调用返回所有股票当日财务数据（市值/PE/换手率等）
    """
    df = pro.daily_basic(trade_date=trade_date)
    if df is None or df.empty:
        return {'status': 'no_data', 'rows': 0}

    df = df.sort_values('ts_code')
    total = len(df)
    print(f"  全市场财务：获取到 {total} 条记录")

    daily_basic_dir = root / 'data' / 'daily_basic'
    daily_basic_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for ts_code in df['ts_code'].unique():
        code_df = df[df['ts_code'] == ts_code].copy()
        path = daily_basic_dir / f'{ts_code}.csv'
        if path.exists():
            existing = pd.read_csv(path, dtype=str)
            merged = pd.concat([existing, code_df]).drop_duplicates(subset='trade_date', keep='last')
            merged = merged.sort_values('trade_date')
            merged.to_csv(path, index=False)
        else:
            code_df.to_csv(path, index=False)
        written += 1

    return {'status': 'ok', 'rows': total, 'files_written': written}


def sync_index_daily(pro, trade_date: str, root: Path) -> dict:
    """同步上证指数"""
    # 拉最近30天确保有足够数据计算market_regime
    start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=35)).strftime('%Y%m%d')
    df = pro.index_daily(ts_code='000001.SH', start_date=start, end_date=trade_date)
    if df is None or df.empty:
        return {'status': 'no_data'}

    df = df.sort_values('trade_date')
    path = root / 'data' / 'index_daily' / '000001.SH.csv'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = pd.read_csv(path, dtype=str)
        merged = pd.concat([existing, df]).drop_duplicates(subset='trade_date', keep='last')
        merged = merged.sort_values('trade_date')
        merged.to_csv(path, index=False)
    else:
        df.to_csv(path, index=False)
    return {'status': 'ok', 'rows': len(df)}


def main():
    settings = load_settings()
    trade_date = get_trade_date()
    today_str = datetime.now().strftime('%Y-%m-%d %H:%M')

    print(f"\n=== 每日数据同步（全市场版）===")
    print(f"目标交易日: {trade_date}")
    print(f"执行时间: {today_str}")

    token = settings['data']['tushare_token']
    pro = ts.pro_api(token)

    # 1. 上证指数（必选）
    print("\n[1/3] 同步上证指数...")
    r = sync_index_daily(pro, trade_date, ROOT)
    if r['status'] == 'ok':
        print(f"  [OK] 上证指数已更新 {r['rows']} 条")
    else:
        print(f"  [WARN] 上证指数无数据（可能是非交易日）")

    # 2. 全市场日线（核心！5000+股票）
    print("\n[2/3] 同步全市场日线（约5500只）...")
    r = sync_market_daily(pro, trade_date, ROOT)
    if r['status'] == 'ok':
        print(f"  [OK] 全市场日线完成：{r['rows']} 条，{r['files_written']} 个股票文件已写入/更新")
    else:
        print(f"  [WARN] 全市场日线无数据")

    # 3. 全市场财务数据
    print("\n[3/3] 同步全市场财务数据...")
    r = sync_market_daily_basic(pro, trade_date, ROOT)
    if r['status'] == 'ok':
        print(f"  [OK] 全市场财务完成：{r['rows']} 条，{r['files_written']} 个股票文件已写入/更新")
    else:
        print(f"  [WARN] 全市场财务无数据")

    print(f"\n=== 数据同步完成 {trade_date} ===")

    # 4. 验证最新数据
    print("\n[验证] 检查最新数据日期...")
    index_path = ROOT / 'data' / 'index_daily' / '000001.SH.csv'
    if index_path.exists():
        idx_tail = pd.read_csv(index_path, dtype=str).tail(1).iloc[0]
        print(f"  上证指数最新：{idx_tail['trade_date']}")

    sample_codes = ['002756.SZ', '000568.SZ']
    for code in sample_codes:
        p = ROOT / 'data' / 'daily' / code
        if p.exists():
            tail = pd.read_csv(p, dtype=str).tail(1).iloc[0]
            print(f"  {code} 最新：{tail['trade_date']} 收盘:{tail['close']}")


if __name__ == '__main__':
    main()
