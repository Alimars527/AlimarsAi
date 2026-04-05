#!/usr/bin/env python3
import json
import sys
import time
from pathlib import Path

import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.config import load_settings
from quant.history_sync import HistorySync

START_DATE = '20000101'
END_DATE = '20260330'
STATE_PATH = project_root / 'outputs' / 'daily_integrity_repair_state_20000101_20260330.json'
PROGRESS_PATH = project_root / 'outputs' / 'daily_integrity_repair_progress_20000101_20260330.json'
DETAIL_PATH = project_root / 'outputs' / 'daily_integrity_repair_missing_20000101_20260330.csv'
STATE_JSONL = project_root / 'outputs' / 'daily_integrity_repair_state_20000101_20260330.jsonl'


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding='utf-8'))
    return {
        'start_date': START_DATE,
        'end_date': END_DATE,
        'completed_codes': [],
        'failed_codes': {},
        'repaired_codes': [],
        'scan_started_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def write_progress(progress):
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')


def append_jsonl(obj):
    with STATE_JSONL.open('a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def expected_dates(index_dates, list_date):
    return [d for d in index_dates if d >= list_date and d <= END_DATE]


def analyze_missing(code, list_date, daily_path, trading_dates):
    exp = expected_dates(trading_dates, list_date)
    if not daily_path.exists():
        return exp, []
    daily = pd.read_csv(daily_path, dtype=str, usecols=['trade_date'])
    present = sorted(set(daily['trade_date'].astype(str)))
    present_set = set(present)
    missing = [d for d in exp if d not in present_set]
    return missing, present


def main():
    settings = load_settings()
    sync = HistorySync(settings['data']['tushare_token'], str(project_root))
    store = sync.store

    stock_basic = pd.read_csv(project_root / 'data' / 'meta' / 'stock_basic.csv', dtype=str)
    stock_basic = stock_basic[~stock_basic['ts_code'].astype(str).str.endswith('.BJ')].copy()
    stock_basic['list_date'] = stock_basic['list_date'].fillna(START_DATE).astype(str)
    stock_basic = stock_basic.sort_values(['list_date', 'ts_code']).reset_index(drop=True)

    index_df = store.load('index_daily', '000001.SH')
    trading_dates = sorted(d for d in index_df['trade_date'].astype(str).tolist() if START_DATE <= d <= END_DATE)
    if not trading_dates:
        raise SystemExit('index_daily/000001.SH 缺失，无法构造交易日历')

    state = load_state()
    completed = set(state.get('completed_codes', []))
    repaired = set(state.get('repaired_codes', []))
    failed = state.get('failed_codes', {})

    total = len(stock_basic)
    detail_rows = []
    for _, row in stock_basic.iterrows():
        code = row['ts_code']
        name = row.get('name', '')
        industry = row.get('industry', '')
        list_date = max(str(row.get('list_date', START_DATE)), START_DATE)
        daily_path = project_root / 'data' / 'daily' / f'{code}.csv'
        missing, present = analyze_missing(code, list_date, daily_path, trading_dates)
        detail_rows.append({
            'code': code,
            'name': name,
            'industry': industry,
            'list_date': list_date,
            'expected_count': len(expected_dates(trading_dates, list_date)),
            'present_count': len([d for d in present if d >= list_date and d <= END_DATE]),
            'missing_count': len(missing),
            'missing_start': missing[0] if missing else '',
            'missing_end': missing[-1] if missing else '',
            'missing_dates_preview': ','.join(missing[:20]),
        })
    pd.DataFrame(detail_rows).to_csv(DETAIL_PATH, index=False)

    remaining = [r for _, r in stock_basic.iterrows() if r['ts_code'] not in completed]
    processed = len(completed)
    for row in remaining:
        code = row['ts_code']
        name = row.get('name', '')
        industry = row.get('industry', '')
        list_date = max(str(row.get('list_date', START_DATE)), START_DATE)
        try:
            daily_path = project_root / 'data' / 'daily' / f'{code}.csv'
            missing_before, _ = analyze_missing(code, list_date, daily_path, trading_dates)
            repaired_now = False
            if missing_before:
                sync.sync_daily_for_code(code, list_date, END_DATE)
                repaired_now = True
            missing_after, _ = analyze_missing(code, list_date, daily_path, trading_dates)
            completed.add(code)
            if repaired_now:
                repaired.add(code)
            failed.pop(code, None)
            processed += 1
            progress = {
                'task': 'fullmarket_daily_integrity_repair',
                'start_date': START_DATE,
                'end_date': END_DATE,
                'total_codes': total,
                'processed_codes': processed,
                'completed_codes': len(completed),
                'repaired_codes': len(repaired),
                'failed_codes': len(failed),
                'progress_pct': round(processed / total * 100, 2),
                'current_code': code,
                'current_name': name,
                'current_industry': industry,
                'missing_before': len(missing_before),
                'missing_after': len(missing_after),
                'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            state['completed_codes'] = sorted(completed)
            state['repaired_codes'] = sorted(repaired)
            state['failed_codes'] = failed
            save_state(state)
            write_progress(progress)
            append_jsonl(progress)
            print(progress)
        except Exception as e:
            failed[code] = str(e)
            state['failed_codes'] = failed
            save_state(state)
            append_jsonl({
                'task': 'fullmarket_daily_integrity_repair',
                'code': code,
                'name': name,
                'status': 'failed',
                'error': str(e),
                'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            })


if __name__ == '__main__':
    main()
