import sys
import json
import time
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import pandas as pd
from quant.config import load_settings
from quant.history_sync import HistorySync

STATE_PATH = project_root / 'data' / 'meta' / 'backfill_state_20230101_20241231.json'
START_DATE = '20230101'
END_DATE = '20241231'


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding='utf-8'))
    return {
        'completed_codes': [],
        'failed_codes': [],
        'start_date': START_DATE,
        'end_date': END_DATE,
    }


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def merge_prepend(csv_path: Path, new_df: pd.DataFrame):
    if new_df is None or new_df.empty:
        return
    if csv_path.exists():
        old_df = pd.read_csv(csv_path, dtype=str)
        merged = pd.concat([old_df, new_df], ignore_index=True)
        subset = ['trade_date'] if 'trade_date' in merged.columns else None
        if subset:
            merged = merged.drop_duplicates(subset=subset, keep='last').sort_values('trade_date')
        else:
            merged = merged.drop_duplicates()
        merged.to_csv(csv_path, index=False)
    else:
        new_df.to_csv(csv_path, index=False)


def main():
    settings = load_settings()
    token = settings['data']['tushare_token']
    sync = HistorySync(token, str(project_root))

    stock_basic_path = project_root / 'data' / 'meta' / 'stock_basic.csv'
    stock_basic = pd.read_csv(stock_basic_path, dtype=str)
    codes = [c for c in stock_basic['ts_code'].dropna().tolist() if not c.endswith('.BJ')]

    state = load_state()
    completed = set(state.get('completed_codes', []))
    failed = set(state.get('failed_codes', []))

    remaining = [c for c in codes if c not in completed]
    print(f'backfill_total={len(codes)} completed={len(completed)} remaining={len(remaining)}')

    # index backfill
    idx_df = sync.loader.get_index_daily('000001.SH', START_DATE, END_DATE)
    if idx_df is not None and not idx_df.empty:
        merge_prepend(project_root / 'data' / 'index_daily' / '000001.SH.csv', idx_df.sort_values('trade_date'))

    for i, code in enumerate(remaining, 1):
        try:
            daily = sync.loader.get_daily(code, START_DATE, END_DATE)
            if daily is not None and not daily.empty:
                merge_prepend(project_root / 'data' / 'daily' / f'{code}.csv', daily.sort_values('trade_date'))
            daily_basic = sync.loader.get_daily_basic(code, START_DATE, END_DATE)
            if daily_basic is not None and not daily_basic.empty:
                merge_prepend(project_root / 'data' / 'daily_basic' / f'{code}.csv', daily_basic.sort_values('trade_date'))
            adj = sync.loader.get_adj_factor(code, START_DATE, END_DATE)
            if adj is not None and not adj.empty:
                merge_prepend(project_root / 'data' / 'adj_factor' / f'{code}.csv', adj.sort_values('trade_date'))

            completed.add(code)
            failed.discard(code)
            state['completed_codes'] = sorted(completed)
            state['failed_codes'] = sorted(failed)
            save_state(state)
            if i % 25 == 0:
                print(f'progress\t{i}/{len(remaining)}\tcode={code}\tcompleted={len(completed)}')
            time.sleep(0.02)
        except Exception as e:
            failed.add(code)
            state['failed_codes'] = sorted(failed)
            save_state(state)
            print(f'error\t{code}\t{str(e).splitlines()[0][:160]}')
            time.sleep(0.1)

    print('backfill_finished')
    print(f'completed={len(completed)} failed={len(failed)} total={len(codes)}')


if __name__ == '__main__':
    main()
