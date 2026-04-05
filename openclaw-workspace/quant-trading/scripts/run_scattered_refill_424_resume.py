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
from quant.local_data_store import LocalDataStore

STATE_PATH = ROOT / 'outputs' / 'scattered_refill_424_state.json'
PROGRESS_PATH = ROOT / 'outputs' / 'scattered_refill_424_progress.json'
RESULTS_PATH = ROOT / 'outputs' / 'scattered_refill_424_results.csv'
VERIFY_PATH = ROOT / 'outputs' / 'scattered_refill_424_verify.csv'
TARGETS_PATH = ROOT / 'outputs' / 'remaining_missing_scattered_refill_424_20260401.csv'
TRADE_CAL_PATH = ROOT / 'data' / 'index_daily' / '000001.SH.csv'
START_DATE = '20000101'
END_DATE = '20260330'
SEGMENTS = [
    ('20000101', '20041231'),
    ('20050101', '20091231'),
    ('20100101', '20141231'),
    ('20150101', '20191231'),
    ('20200101', '20221231'),
    ('20230101', '20260330'),
]
REQUEST_INTERVAL_SECONDS = 1.0
BATCH_SIZE = 20


def load_state(targets):
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding='utf-8'))
    else:
        state = {'started_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'completed_codes': [], 'failed_codes': [], 'last_index': 0}
    state.setdefault('completed_codes', [])
    state.setdefault('failed_codes', [])
    state.setdefault('last_index', 0)
    return state


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def save_progress(state, total, repaired_count, still_missing_count):
    completed = len(state['completed_codes'])
    failed = len(state['failed_codes'])
    pct = round(completed / total * 100, 2) if total else 100.0
    progress = {
        'task': 'scattered_refill_424',
        'status': 'running',
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_target_codes': total,
        'completed_codes': completed,
        'failed_codes': failed,
        'repaired_codes': repaired_count,
        'still_missing_codes': still_missing_count,
        'progress_pct': pct,
    }
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')


def verify_code(store, code, list_date, trade_dates):
    df = store.load('daily', code)
    present = set(df.get('trade_date', pd.Series(dtype=str)).astype(str).tolist()) if not df.empty else set()
    expected = {d for d in trade_dates if d >= list_date and d <= END_DATE}
    missing = sorted(expected - present)
    return {
        'code': code,
        'present_count': len(present & expected),
        'expected_count': len(expected),
        'missing_count': len(missing),
        'first_missing_date': missing[0] if missing else '',
        'last_missing_date': missing[-1] if missing else '',
    }


def main():
    settings = load_settings()
    sync = HistorySync(settings['data']['tushare_token'], str(ROOT))
    store = LocalDataStore(ROOT / 'data')
    targets = pd.read_csv(TARGETS_PATH, dtype=str).fillna('')
    stock_basic = pd.read_csv(ROOT / 'data' / 'meta' / 'stock_basic.csv', dtype=str).fillna('')
    list_dates = dict(zip(stock_basic['ts_code'].astype(str), stock_basic['list_date'].astype(str)))
    trade_cal = pd.read_csv(TRADE_CAL_PATH, dtype=str)
    trade_dates = set(trade_cal[(trade_cal['trade_date'] >= START_DATE) & (trade_cal['trade_date'] <= END_DATE)]['trade_date'].astype(str))

    state = load_state(targets['code'].tolist())
    done = set(state['completed_codes'])
    failed = set(state['failed_codes'])
    results_map = {r['code']: r for r in pd.read_csv(RESULTS_PATH, dtype=str).fillna('').to_dict(orient='records')} if RESULTS_PATH.exists() else {}
    verify_map = {r['code']: r for r in pd.read_csv(VERIFY_PATH, dtype=str).fillna('').to_dict(orient='records')} if VERIFY_PATH.exists() else {}

    total = len(targets)
    for idx, row in enumerate(targets.itertuples(index=False), start=1):
        code = row.code
        if code in done:
            continue
        try:
            seg_stats = []
            for seg_start, seg_end in SEGMENTS:
                daily_df = sync.loader.get_daily(code, seg_start, seg_end)
                if daily_df is not None and not daily_df.empty:
                    store.append_dedup('daily', code, daily_df, subset=('trade_date',))
                seg_stats.append({'start': seg_start, 'end': seg_end, 'rows': 0 if daily_df is None else len(daily_df)})
                time.sleep(REQUEST_INTERVAL_SECONDS)
            verify = verify_code(store, code, list_dates.get(code, START_DATE) or START_DATE, trade_dates)
            verify_map[code] = {'code': code, 'name': row.name, 'industry': row.industry, 'original_missing_count': int(row.missing_count), **verify}
            results_map[code] = {'code': code, 'name': row.name, 'industry': row.industry, 'status': 'ok', 'segments': json.dumps(seg_stats, ensure_ascii=False), 'original_missing_count': int(row.missing_count), 'remaining_missing_count': verify['missing_count']}
            done.add(code)
            failed.discard(code)
        except Exception as e:
            results_map[code] = {'code': code, 'name': row.name, 'industry': row.industry, 'status': 'failed', 'error': str(e), 'original_missing_count': int(row.missing_count)}
            failed.add(code)
        state['completed_codes'] = sorted(done)
        state['failed_codes'] = sorted(failed)
        state['last_index'] = idx
        if idx % BATCH_SIZE == 0 or idx == total:
            pd.DataFrame(results_map.values()).to_csv(RESULTS_PATH, index=False)
            pd.DataFrame(verify_map.values()).to_csv(VERIFY_PATH, index=False)
            repaired_count = sum(1 for r in verify_map.values() if int(r['missing_count']) == 0)
            still_missing_count = sum(1 for r in verify_map.values() if int(r['missing_count']) > 0)
            save_state(state)
            save_progress(state, total, repaired_count, still_missing_count)

    pd.DataFrame(results_map.values()).to_csv(RESULTS_PATH, index=False)
    pd.DataFrame(verify_map.values()).to_csv(VERIFY_PATH, index=False)
    repaired_count = sum(1 for r in verify_map.values() if int(r['missing_count']) == 0)
    still_missing_count = sum(1 for r in verify_map.values() if int(r['missing_count']) > 0)
    save_state(state)
    save_progress(state, total, repaired_count, still_missing_count)
    progress = json.loads(PROGRESS_PATH.read_text(encoding='utf-8'))
    progress['status'] = 'completed'
    progress['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')
    print(PROGRESS_PATH)
    print(RESULTS_PATH)
    print(VERIFY_PATH)


if __name__ == '__main__':
    main()
