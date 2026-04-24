#!/usr/bin/env python3
"""
批量历史数据同步脚本（断点续传版）
从2022年初开始，逐日拉取全市场日线+daily_basic数据
写入data/daily/和data/daily_basic/的分股票CSV（merge去重）

用法: python3 -u sync_history_full.py
支持断点续传：记录进度到 sync_history_progress.json
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
import pandas as pd
import tushare as ts

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.config import load_settings

PROGRESS_FILE = ROOT / 'scripts' / 'backfill_2020_2022_progress.json'
START_DATE = '20200101'
END_DATE = '20220103'  # 补到现有数据开始前一天
BATCH_INTERVAL = 0.35  # 每次调用间隔（秒），防止触发限频


def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {'completed_dates': [], 'last_update': None}


def save_progress(progress):
    progress['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)


def sync_one_day(pro, trade_date, root):
    """同步单日全市场数据（daily + daily_basic）"""
    results = {'date': trade_date, 'daily': 0, 'daily_basic': 0}

    # 1. daily
    try:
        df = pro.daily(trade_date=trade_date)
        if df is not None and not df.empty:
            daily_dir = root / 'data' / 'daily'
            daily_dir.mkdir(parents=True, exist_ok=True)
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
            results['daily'] = len(df)
    except Exception as e:
        print(f"  [ERROR] daily {trade_date}: {e}")

    # 2. daily_basic
    try:
        df = pro.daily_basic(trade_date=trade_date)
        if df is not None and not df.empty:
            daily_basic_dir = root / 'data' / 'daily_basic'
            daily_basic_dir.mkdir(parents=True, exist_ok=True)
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
            results['daily_basic'] = len(df)
    except Exception as e:
        print(f"  [ERROR] daily_basic {trade_date}: {e}")

    return results


def main():
    settings = load_settings()
    token = settings['data']['tushare_token']
    pro = ts.pro_api(token)

    print("=== 批量历史数据同步 ===")
    print(f"范围: {START_DATE} ~ {END_DATE}")

    # 获取交易日历
    cal_df = pro.trade_cal(exchange='SSE', start_date=START_DATE, end_date=END_DATE)
    cal_df = cal_df[cal_df['is_open'] == 1].sort_values('cal_date')
    all_dates = cal_df['cal_date'].tolist()
    print(f"交易日总数: {len(all_dates)}")

    # 加载进度
    progress = load_progress()
    completed = set(progress['completed_dates'])
    remaining = [d for d in all_dates if d not in completed]
    print(f"已完成: {len(completed)}, 剩余: {len(remaining)}")

    if not remaining:
        print("全部已完成，无需同步。")
        return

    # 逐日同步
    for i, trade_date in enumerate(remaining, 1):
        r = sync_one_day(pro, trade_date, ROOT)
        completed.add(trade_date)
        progress['completed_dates'] = sorted(list(completed))

        # 每10天存一次进度
        if i % 10 == 0:
            save_progress(progress)

        total_done = len(completed)
        pct = total_done / len(all_dates) * 100
        print(f"[{total_done}/{len(all_dates)}] ({pct:.1f}%) {trade_date}: daily={r['daily']} basic={r['daily_basic']}")

        time.sleep(BATCH_INTERVAL)

    # 最终保存
    save_progress(progress)
    print(f"\n=== 同步完成 ===")
    print(f"总计: {len(completed)}/{len(all_dates)} 个交易日")

    # 验证
    sample = ROOT / 'data' / 'daily' / '600519.SH.csv'
    if sample.exists():
        df = pd.read_csv(sample, dtype=str)
        print(f"验证 600519.SH: {len(df)}行, {df['trade_date'].min()}~{df['trade_date'].max()}")


if __name__ == '__main__':
    main()
