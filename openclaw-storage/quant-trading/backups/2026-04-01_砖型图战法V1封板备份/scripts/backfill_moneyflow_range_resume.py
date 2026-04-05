import sys
import json
import time
from collections import deque
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import pandas as pd
from quant.config import load_settings
from quant.history_sync import HistorySync


def merge_prepend(csv_path: Path, new_df: pd.DataFrame):
    if new_df is None or new_df.empty:
        return
    if csv_path.exists():
        old_df = pd.read_csv(csv_path, dtype=str)
        merged = pd.concat([old_df, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=['trade_date'], keep='last').sort_values('trade_date')
        merged.to_csv(csv_path, index=False)
    else:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        new_df.sort_values('trade_date').to_csv(csv_path, index=False)


def main(start_date: str, end_date: str):
    state_path = project_root / 'data' / 'meta' / f'moneyflow_state_{start_date}_{end_date}.json'
    request_times = deque()

    def load_state():
        if state_path.exists():
            return json.loads(state_path.read_text(encoding='utf-8'))
        return {'completed_codes': [], 'failed_codes': [], 'start_date': start_date, 'end_date': end_date}

    def save_state(state):
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

    def wait_for_rate_limit():
        now = time.time()
        while request_times and now - request_times[0] >= 60:
            request_times.popleft()
        if len(request_times) >= 299:
            sleep_sec = 60 - (now - request_times[0]) + 0.5
            if sleep_sec > 0:
                print(f'rate_limit_wait\t{sleep_sec:.1f}s')
                time.sleep(sleep_sec)
        now = time.time()
        while request_times and now - request_times[0] >= 60:
            request_times.popleft()
        request_times.append(time.time())

    settings = load_settings()
    token = settings['data']['tushare_token']
    sync = HistorySync(token, str(project_root))

    stock_basic_path = project_root / 'data' / 'meta' / 'stock_basic.csv'
    stock_basic = pd.read_csv(stock_basic_path, dtype=str)
    codes = [c for c in stock_basic['ts_code'].dropna().tolist() if not c.endswith('.BJ')]

    state = load_state()
    completed = set(state.get('completed_codes', []))
    failed = set(state.get('failed_codes', []))
    # 失败列表只做暂存，允许后续重试；本次重新从未完成的开始
    remaining = [c for c in codes if c not in completed]
    print(f'moneyflow_total={len(codes)} completed={len(completed)} remaining={len(remaining)} range={start_date}-{end_date}')

    for i, code in enumerate(remaining, 1):
        max_retry = 6
        success = False
        for attempt in range(1, max_retry + 1):
            try:
                wait_for_rate_limit()
                df = sync.loader.get_moneyflow(code, start_date, end_date)
                if df is not None and not df.empty:
                    merge_prepend(project_root / 'data' / 'moneyflow' / f'{code}.csv', df)
                completed.add(code)
                failed.discard(code)
                state['completed_codes'] = sorted(completed)
                state['failed_codes'] = sorted(failed)
                save_state(state)
                success = True
                break
            except Exception as e:
                msg = str(e).splitlines()[0][:160]
                if '每分钟最多访问该接口300次' in msg:
                    sleep_sec = 65 + min(attempt * 5, 30)
                    print(f'rate_limit\t{code}\tattempt={attempt}\twait={sleep_sec}s')
                    time.sleep(sleep_sec)
                    continue
                if attempt < max_retry:
                    print(f'retry\t{code}\tattempt={attempt}\t{msg}')
                    time.sleep(min(2 * attempt, 10))
                    continue
                failed.add(code)
                state['failed_codes'] = sorted(failed)
                save_state(state)
                print(f'error\t{code}\t{msg}')
        if i % 25 == 0:
            print(f'progress\t{i}/{len(remaining)}\tcode={code}\tcompleted={len(completed)}\tfailed={len(failed)}')
        if not success:
            time.sleep(0.2)

    print('moneyflow_backfill_finished')
    print(f'completed={len(completed)} failed={len(failed)} total={len(codes)} range={start_date}-{end_date}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python backfill_moneyflow_range_resume.py <START_DATE> <END_DATE>')
    main(sys.argv[1], sys.argv[2])
