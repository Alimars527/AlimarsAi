import sys
import json
import time
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import pandas as pd
from quant.config import load_settings
from quant.history_sync import HistorySync

STATE_PATH = project_root / 'data' / 'meta' / 'sync_state.json'
START_DATE = '20250101'
END_DATE = '20260320'


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding='utf-8'))
    return {
        'completed_codes': [],
        'failed_codes': [],
        'last_index': 0,
        'start_date': START_DATE,
        'end_date': END_DATE,
    }


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    settings = load_settings()
    token = settings['data']['tushare_token']
    sync = HistorySync(token, str(project_root))

    sync.sync_stock_basic()
    sync.sync_index_daily('000001.SH', START_DATE, END_DATE)

    stock_basic_path = project_root / 'data' / 'meta' / 'stock_basic.csv'
    stock_basic = pd.read_csv(stock_basic_path, dtype=str)
    codes = stock_basic['ts_code'].dropna().tolist()

    filtered = []
    for c in codes:
        if c.endswith('.BJ'):
            continue
        filtered.append(c)

    state = load_state()
    completed = set(state.get('completed_codes', []))
    failed = set(state.get('failed_codes', []))

    # 自动识别已存在完整三件套的股票，避免重复下载
    for code in filtered:
        daily_ok = (project_root / 'data' / 'daily' / f'{code}.csv').exists()
        basic_ok = (project_root / 'data' / 'daily_basic' / f'{code}.csv').exists()
        adj_ok = (project_root / 'data' / 'adj_factor' / f'{code}.csv').exists()
        if daily_ok and basic_ok and adj_ok:
            completed.add(code)

    state['completed_codes'] = sorted(completed)
    state['failed_codes'] = sorted(failed)
    save_state(state)

    total = len(filtered)
    remaining = [c for c in filtered if c not in completed]
    print(f'total={total} completed={len(completed)} remaining={len(remaining)}')

    for idx, code in enumerate(remaining, 1):
        try:
            result = sync.sync_bundle_for_code(code, START_DATE, END_DATE)
            completed.add(code)
            if code in failed:
                failed.remove(code)
            state['completed_codes'] = sorted(completed)
            state['failed_codes'] = sorted(failed)
            state['last_index'] = len(completed)
            save_state(state)
            if idx % 25 == 0:
                print(f'progress\t{idx}/{len(remaining)}\tcode={code}\tcompleted={len(completed)}')
            time.sleep(0.02)
        except Exception as e:
            failed.add(code)
            state['failed_codes'] = sorted(failed)
            save_state(state)
            print(f'error\t{code}\t{str(e).splitlines()[0][:160]}')
            time.sleep(0.1)

    print('sync_finished')
    print(f'completed={len(completed)} failed={len(failed)} total={total}')


if __name__ == '__main__':
    main()
