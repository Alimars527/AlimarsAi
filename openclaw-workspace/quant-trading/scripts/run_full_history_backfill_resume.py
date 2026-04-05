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

STATE_PATH = ROOT / 'outputs' / 'full_history_backfill_state.json'
PROGRESS_PATH = ROOT / 'outputs' / 'full_history_backfill_progress.json'
RESULTS_PATH = ROOT / 'outputs' / 'full_history_backfill_results.csv'
GAP_RESULTS_PATH = ROOT / 'outputs' / 'full_history_gap_scan_results.csv'
START_DATE = '20000101'
END_DATE = '20260330'
BATCH_SIZE = 20
REQUEST_INTERVAL_SECONDS = 2.0
RATE_LIMIT_SLEEP_SECONDS = 35
MAX_RETRIES = 3


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
    return state


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def save_progress(state, total, results_rows):
    completed = len(state['completed_codes'])
    failed = len(state['failed_codes'])
    pct = round(completed / total * 100, 2) if total else 100.0
    remaining = max(total - completed, 0)
    progress = {
        'task': 'full_history_backfill',
        'status': 'running',
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'window': {'start_date': START_DATE, 'end_date': END_DATE},
        'target_codes': total,
        'completed_codes': completed,
        'failed_codes': failed,
        'remaining_codes': remaining,
        'progress_pct': pct,
    }
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')
    pd.DataFrame(results_rows).to_csv(RESULTS_PATH, index=False)


def is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc)
    return '每分钟最多访问该接口200次' in msg or '最多访问该接口200次' in msg


def main():
    if not GAP_RESULTS_PATH.exists():
        raise SystemExit(f'missing gap results: {GAP_RESULTS_PATH}')
    settings = load_settings()
    sync = HistorySync(settings['data']['tushare_token'], str(ROOT))

    gaps = pd.read_csv(GAP_RESULTS_PATH, dtype=str).fillna('')
    targets = gaps[gaps['missing_count'].astype(int) > 0]['code'].astype(str).tolist()
    state = load_state(targets)
    done = set(state['completed_codes'])
    failed = set(state['failed_codes'])
    existing = pd.read_csv(RESULTS_PATH, dtype=str).fillna('') if RESULTS_PATH.exists() else pd.DataFrame()
    results_map = {r['code']: r for r in existing.to_dict(orient='records')} if not existing.empty else {}

    for idx, code in enumerate(targets, start=1):
        if code in done:
            continue
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                bundle = sync.sync_bundle_for_code(code, START_DATE, END_DATE)
                results_map[code] = {
                    'code': code,
                    'status': 'ok',
                    'daily_rows': str(bundle['daily'].get('rows', 0)),
                    'daily_basic_rows': str(bundle['daily_basic'].get('rows', 0)),
                    'adj_factor_rows': str(bundle['adj_factor'].get('rows', 0)),
                    'moneyflow_rows': str(bundle['moneyflow'].get('rows', 0)),
                    'hkhold_rows': str(bundle['hkhold'].get('rows', 0)),
                    'margin_detail_rows': str(bundle['margin_detail'].get('rows', 0)),
                    'attempts': str(attempt),
                }
                done.add(code)
                failed.discard(code)
                last_error = None
                break
            except Exception as e:
                last_error = e
                if is_rate_limit_error(e) and attempt < MAX_RETRIES:
                    time.sleep(RATE_LIMIT_SLEEP_SECONDS)
                    continue
                break
        if last_error is not None:
            results_map[code] = {
                'code': code,
                'status': 'failed',
                'error': str(last_error),
                'attempts': str(MAX_RETRIES if is_rate_limit_error(last_error) else 1),
            }
            failed.add(code)
        time.sleep(REQUEST_INTERVAL_SECONDS)
        state['completed_codes'] = sorted(done)
        state['failed_codes'] = sorted(failed)
        state['last_index'] = idx
        if idx % BATCH_SIZE == 0 or idx == len(targets):
            save_state(state)
            save_progress(state, len(targets), list(results_map.values()))

    save_state(state)
    progress = json.loads(PROGRESS_PATH.read_text(encoding='utf-8')) if PROGRESS_PATH.exists() else {}
    progress['status'] = 'completed'
    progress['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')
    pd.DataFrame(results_map.values()).to_csv(RESULTS_PATH, index=False)
    print(PROGRESS_PATH)
    print(RESULTS_PATH)


if __name__ == '__main__':
    main()
