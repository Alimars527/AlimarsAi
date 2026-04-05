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
    state_path = project_root / 'data' / 'meta' / f'hkhold_state_{start_date}_{end_date}.json'
    if not state_path.exists():
        raise SystemExit(f'state file not found: {state_path}')

    state = json.loads(state_path.read_text(encoding='utf-8'))
    failed = list(state.get('failed_codes', []))
    completed = set(state.get('completed_codes', []))
    still_failed = set()
    request_times = deque()

    def save_state():
        state['completed_codes'] = sorted(completed)
        state['failed_codes'] = sorted(still_failed)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

    def wait_for_rate_limit():
        now = time.time()
        while request_times and now - request_times[0] >= 60:
            request_times.popleft()
        if len(request_times) >= 120:
            sleep_sec = 60 - (now - request_times[0]) + 1.2
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

    print(f'retry_failed_total={len(failed)} range={start_date}-{end_date}')
    for i, code in enumerate(failed, 1):
        success = False
        max_retry = 6
        for attempt in range(1, max_retry + 1):
            try:
                wait_for_rate_limit()
                df = sync.loader.get_hkhold(code, start_date, end_date)
                if df is not None and not df.empty:
                    merge_prepend(project_root / 'data' / 'hkhold' / f'{code}.csv', df)
                completed.add(code)
                success = True
                break
            except Exception as e:
                msg = str(e).splitlines()[0][:200]
                if '每分钟最多访问该接口200次' in msg:
                    sleep_sec = 70 + min(attempt * 8, 40)
                    print(f'rate_limit\t{code}\tattempt={attempt}\twait={sleep_sec}s')
                    time.sleep(sleep_sec)
                    continue
                if attempt < max_retry:
                    print(f'retry\t{code}\tattempt={attempt}\t{msg}')
                    time.sleep(min(3 * attempt, 15))
                    continue
                print(f'error\t{code}\t{msg}')
        if not success:
            still_failed.add(code)
        save_state()
        print(f'progress\t{i}/{len(failed)}\tcode={code}\tsuccess={success}\tremaining_failed={len(still_failed)}')

    print('retry_hkhold_failed_finished')
    print(f'final_failed={len(still_failed)} total_failed_input={len(failed)}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python retry_hkhold_failed.py <START_DATE> <END_DATE>')
    main(sys.argv[1], sys.argv[2])
