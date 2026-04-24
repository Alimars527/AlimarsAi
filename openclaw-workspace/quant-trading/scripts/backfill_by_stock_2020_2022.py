#!/usr/bin/env python3
"""
按股票分段补历史数据（2020-01-01 ~ 2022-01-03）
每只股票一次拉取整段，merge去重后写入CSV
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

PROGRESS_FILE = ROOT / 'scripts' / 'backfill_by_stock_2020_2022_progress.json'
START_DATE = '20200101'
END_DATE = '20220103'
BATCH_INTERVAL = 0.25  # 每次调用间隔（秒）
BATCH_SAVE = 50        # 每50只保存一次进度


def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {'completed_codes': [], 'errors': {}, 'last_update': None}


def save_progress(progress):
    progress['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def sync_one_stock(pro, ts_code, root):
    """同步单只股票的历史数据"""
    results = {'code': ts_code, 'daily_rows': 0, 'daily_basic_rows': 0, 'error': None}

    # 1. daily
    try:
        df = pro.daily(ts_code=ts_code, start_date=START_DATE, end_date=END_DATE)
        if df is not None and not df.empty:
            daily_dir = root / 'data' / 'daily'
            daily_dir.mkdir(parents=True, exist_ok=True)
            path = daily_dir / f'{ts_code}.csv'
            if path.exists():
                existing = pd.read_csv(path, dtype=str)
                merged = pd.concat([existing, df]).drop_duplicates(subset='trade_date', keep='last')
                merged = merged.sort_values('trade_date')
                merged.to_csv(path, index=False)
            else:
                df.to_csv(path, index=False)
            results['daily_rows'] = len(df)
    except Exception as e:
        results['error'] = f'daily: {e}'
        return results

    # 2. daily_basic
    try:
        df = pro.daily_basic(ts_code=ts_code, start_date=START_DATE, end_date=END_DATE)
        if df is not None and not df.empty:
            daily_basic_dir = root / 'data' / 'daily_basic'
            daily_basic_dir.mkdir(parents=True, exist_ok=True)
            path = daily_basic_dir / f'{ts_code}.csv'
            if path.exists():
                existing = pd.read_csv(path, dtype=str)
                merged = pd.concat([existing, df]).drop_duplicates(subset='trade_date', keep='last')
                merged = merged.sort_values('trade_date')
                merged.to_csv(path, index=False)
            else:
                df.to_csv(path, index=False)
            results['daily_basic_rows'] = len(df)
    except Exception as e:
        results['error'] = f'daily_basic: {e}'

    return results


def main():
    settings = load_settings()
    token = settings['data']['tushare_token']
    pro = ts.pro_api(token)

    # 获取所有已有数据的股票代码
    daily_dir = ROOT / 'data' / 'daily'
    all_files = sorted(daily_dir.glob('*.csv'))
    all_codes = [f.stem for f in all_files]
    print(f"=== 按股票分段补历史数据 ===")
    print(f"数据范围: {START_DATE} ~ {END_DATE}")
    print(f"目标股票数: {len(all_codes)}")

    # 加载进度
    progress = load_progress()
    completed = set(progress['completed_codes'])
    remaining = [c for c in all_codes if c not in completed]
    print(f"已完成: {len(completed)}, 剩余: {len(remaining)}")

    if not remaining:
        print("全部已完成，无需同步。")
        return

    total = len(all_codes)
    done_count = len(completed)

    for i, ts_code in enumerate(remaining, 1):
        r = sync_one_stock(pro, ts_code, ROOT)
        done_count += 1

        if r['error']:
            progress['errors'][ts_code] = r['error']
            print(f"[{done_count}/{total}] {ts_code}: ERROR - {r['error']}")
        else:
            completed.add(ts_code)
            progress['completed_codes'] = sorted(list(completed))
            pct = done_count / total * 100
            print(f"[{done_count}/{total}] ({pct:.1f}%) {ts_code}: daily={r['daily_rows']} basic={r['daily_basic_rows']}")

        # 每BATCH_SAVE只保存一次进度
        if i % BATCH_SAVE == 0:
            save_progress(progress)

        time.sleep(BATCH_INTERVAL)

    # 最终保存
    save_progress(progress)
    print(f"\n=== 同步完成 ===")
    print(f"总计: {len(completed)}/{total} 只股票")
    if progress['errors']:
        print(f"错误数: {len(progress['errors'])}")

    # 验证
    sample = ROOT / 'data' / 'daily' / '000001.SZ.csv'
    if sample.exists():
        df = pd.read_csv(sample, dtype=str)
        print(f"验证 000001.SZ: {len(df)}行, {df['trade_date'].min()}~{df['trade_date'].max()}")


if __name__ == '__main__':
    main()
