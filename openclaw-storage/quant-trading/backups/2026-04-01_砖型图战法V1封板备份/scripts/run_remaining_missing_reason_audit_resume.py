#!/usr/bin/env python3
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STATE_PATH = ROOT / 'outputs' / 'remaining_missing_reason_audit_state.json'
PROGRESS_PATH = ROOT / 'outputs' / 'remaining_missing_reason_audit_progress.json'
RESULTS_PATH = ROOT / 'outputs' / 'remaining_missing_reason_audit_results.csv'
TARGETS_PATH = ROOT / 'outputs' / 'remaining_missing_after_backfill_20260401.csv'
TRADE_CAL_PATH = ROOT / 'data' / 'index_daily' / '000001.SH.csv'
STOCK_BASIC_PATH = ROOT / 'data' / 'meta' / 'stock_basic.csv'
DAILY_DIR = ROOT / 'data' / 'daily'
BATCH_SIZE = 50
LONG_GAP_THRESHOLD = 20


def load_state(codes):
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding='utf-8'))
    else:
        state = {'started_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'completed_codes': [], 'last_index': 0}
    state.setdefault('completed_codes', [])
    state.setdefault('last_index', 0)
    return state


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def save_progress(state, total, results):
    completed = len(state['completed_codes'])
    pct = round(completed / total * 100, 2) if total else 100.0
    df = pd.DataFrame(results)
    progress = {
        'task': 'remaining_missing_reason_audit',
        'status': 'running',
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_codes': total,
        'completed_codes': completed,
        'progress_pct': pct,
        'reason_counts': df['reason_tag'].value_counts().to_dict() if not df.empty and 'reason_tag' in df.columns else {},
    }
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')
    df.to_csv(RESULTS_PATH, index=False)


def build_missing_runs(expected, present):
    missing = [d for d in expected if d not in present]
    if not missing:
        return []
    idx_map = {d: i for i, d in enumerate(expected)}
    runs = []
    start = prev = missing[0]
    for d in missing[1:]:
        if idx_map[d] == idx_map[prev] + 1:
            prev = d
        else:
            runs.append((start, prev))
            start = prev = d
    runs.append((start, prev))
    return runs


def main():
    targets = pd.read_csv(TARGETS_PATH, dtype=str).fillna('')
    trade_cal = pd.read_csv(TRADE_CAL_PATH, dtype=str)
    trade_dates = sorted(trade_cal['trade_date'].astype(str).tolist())
    stock_basic = pd.read_csv(STOCK_BASIC_PATH, dtype=str).fillna('')
    list_dates = dict(zip(stock_basic['ts_code'].astype(str), stock_basic['list_date'].astype(str)))

    state = load_state(targets['code'].tolist())
    done = set(state['completed_codes'])
    existing = pd.read_csv(RESULTS_PATH, dtype=str).fillna('').to_dict(orient='records') if RESULTS_PATH.exists() else []
    results_map = {r['code']: r for r in existing}

    total = len(targets)
    for idx, row in enumerate(targets.itertuples(index=False), start=1):
        code = row.code
        if code in done:
            continue
        p = DAILY_DIR / f'{code}.csv'
        df = pd.read_csv(p, dtype=str) if p.exists() else pd.DataFrame(columns=['trade_date'])
        present = set(df.get('trade_date', pd.Series(dtype=str)).astype(str).tolist())
        expected = [d for d in trade_dates if d >= list_dates.get(code, '20000101')]
        runs = build_missing_runs(expected, present)
        long_runs = [r for r in runs if expected.index(r[1]) - expected.index(r[0]) + 1 >= LONG_GAP_THRESHOLD]
        if len(runs) == 0:
            reason = 'no_missing'
        elif len(long_runs) >= 1:
            reason = 'long_suspension_or_restructure'
        elif len(runs) >= 5:
            reason = 'scattered_missing_needs_refill'
        else:
            reason = 'small_gap_needs_manual_check'
        results_map[code] = {
            'code': code,
            'name': row.name,
            'industry': row.industry,
            'missing_count': int(row.missing_count),
            'run_count': len(runs),
            'long_run_count': len(long_runs),
            'first_missing': runs[0][0] if runs else '',
            'last_missing': runs[-1][1] if runs else '',
            'reason_tag': reason,
            'sample_long_runs': json.dumps(long_runs[:5], ensure_ascii=False),
        }
        done.add(code)
        state['completed_codes'] = sorted(done)
        state['last_index'] = idx
        if idx % BATCH_SIZE == 0 or idx == total:
            save_state(state)
            save_progress(state, total, list(results_map.values()))

    save_state(state)
    save_progress(state, total, list(results_map.values()))
    progress = json.loads(PROGRESS_PATH.read_text(encoding='utf-8'))
    progress['status'] = 'completed'
    progress['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')
    print(PROGRESS_PATH)
    print(RESULTS_PATH)


if __name__ == '__main__':
    main()
