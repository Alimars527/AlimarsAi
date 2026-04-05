#!/usr/bin/env python3
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quant.history_sync import HistorySync
from quant.config import load_settings

STATE_PATH = ROOT / 'outputs' / 'full_history_gap_scan_state.json'
PROGRESS_PATH = ROOT / 'outputs' / 'full_history_gap_scan_progress.json'
RESULTS_PATH = ROOT / 'outputs' / 'full_history_gap_scan_results.csv'
TRADE_CAL_PATH = ROOT / 'data' / 'index_daily' / '000001.SH.csv'
START_DATE = '20000101'
END_DATE = '20260330'
BATCH_SIZE = 50


def load_state(codes):
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding='utf-8'))
    else:
        state = {
            'started_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'completed_codes': [],
            'failed_codes': [],
            'last_index': 0,
        }
    state.setdefault('completed_codes', [])
    state.setdefault('failed_codes', [])
    state.setdefault('last_index', 0)
    done = set(state['completed_codes'])
    state['last_index'] = sum(1 for c in codes[:state['last_index']] if c in done)
    return state


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def save_progress(state, total, results_rows):
    completed = len(state['completed_codes'])
    failed = len(state['failed_codes'])
    pct = round(completed / total * 100, 2) if total else 100.0
    missing_codes = sum(1 for r in results_rows if int(r['missing_count']) > 0)
    progress = {
        'task': 'full_history_gap_scan',
        'status': 'running',
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'window': {'start_date': START_DATE, 'end_date': END_DATE},
        'total_codes': total,
        'completed_codes': completed,
        'failed_codes': failed,
        'missing_codes': missing_codes,
        'progress_pct': pct,
    }
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    settings = load_settings()
    sync = HistorySync(settings['data']['tushare_token'], str(ROOT))
    stock_basic = pd.read_csv(ROOT / 'data' / 'meta' / 'stock_basic.csv', dtype=str)
    stock_basic = stock_basic[~stock_basic['ts_code'].astype(str).str.endswith('.BJ', na=False)].copy()
    codes = stock_basic['ts_code'].dropna().astype(str).tolist()
    trade_cal = pd.read_csv(TRADE_CAL_PATH, dtype=str)
    trade_dates = set(trade_cal[(trade_cal['trade_date'] >= START_DATE) & (trade_cal['trade_date'] <= END_DATE)]['trade_date'].astype(str))
    list_dates = dict(zip(stock_basic['ts_code'].astype(str), stock_basic['list_date'].fillna(START_DATE).astype(str)))
    names = dict(zip(stock_basic['ts_code'].astype(str), stock_basic['name'].fillna('').astype(str)))
    industries = dict(zip(stock_basic['ts_code'].astype(str), stock_basic['industry'].fillna('').astype(str)))

    state = load_state(codes)
    done = set(state['completed_codes'])
    failed = set(state['failed_codes'])
    existing_results = pd.read_csv(RESULTS_PATH, dtype=str) if RESULTS_PATH.exists() else pd.DataFrame()
    results_map = {r['code']: r for r in existing_results.to_dict(orient='records')} if not existing_results.empty else {}

    for idx, code in enumerate(codes, start=1):
        if code in done:
            continue
        try:
            daily_path = ROOT / 'data' / 'daily' / f'{code}.csv'
            df = pd.read_csv(daily_path, dtype=str) if daily_path.exists() else pd.DataFrame(columns=['trade_date'])
            present = set(df.get('trade_date', pd.Series(dtype=str)).astype(str).tolist())
            expected = {d for d in trade_dates if d >= list_dates.get(code, START_DATE)}
            missing = sorted(expected - present)
            results_map[code] = {
                'code': code,
                'name': names.get(code, ''),
                'industry': industries.get(code, ''),
                'list_date': list_dates.get(code, ''),
                'present_count': str(len(present & expected)),
                'expected_count': str(len(expected)),
                'missing_count': str(len(missing)),
                'first_missing_date': missing[0] if missing else '',
                'last_missing_date': missing[-1] if missing else '',
            }
            done.add(code)
            failed.discard(code)
        except Exception:
            failed.add(code)
        state['completed_codes'] = sorted(done)
        state['failed_codes'] = sorted(failed)
        state['last_index'] = idx
        if idx % BATCH_SIZE == 0 or idx == len(codes):
            df_out = pd.DataFrame(results_map.values()).sort_values(['missing_count', 'code'], ascending=[False, True])
            df_out.to_csv(RESULTS_PATH, index=False)
            save_state(state)
            save_progress(state, len(codes), list(results_map.values()))

    df_out = pd.DataFrame(results_map.values()).sort_values(['missing_count', 'code'], ascending=[False, True])
    df_out.to_csv(RESULTS_PATH, index=False)
    save_state(state)
    progress = json.loads(PROGRESS_PATH.read_text(encoding='utf-8')) if PROGRESS_PATH.exists() else {}
    progress['status'] = 'completed'
    progress['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')
    print(PROGRESS_PATH)
    print(RESULTS_PATH)


if __name__ == '__main__':
    main()
