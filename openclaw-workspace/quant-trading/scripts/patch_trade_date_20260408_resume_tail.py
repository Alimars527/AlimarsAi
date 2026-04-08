#!/usr/bin/env python3
import json
import time
from pathlib import Path
import pandas as pd
import tushare as ts

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'patch_20260408_full_progress.json'
TOKEN = 'be0e395aeb600a02110bcac4fca37a8d5b792afe8f13507040357d23'
TRADE_DATE = '20260408'
START_PROCESSED = 4860
SLEEP_SEC = 0


def save(status, processed=0, ok=0, fail=0, message=''):
    progress_pct = round(processed / 5194 * 100, 2) if 5194 else 0
    OUT.write_text(json.dumps({
        'task': 'patch_trade_date_20260408_full',
        'trade_date': TRADE_DATE,
        'status': status,
        'processed': processed,
        'total': 5194,
        'progress_pct': progress_pct,
        'ok': ok,
        'fail': fail,
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'message': message,
    }, ensure_ascii=False, indent=2), encoding='utf-8')


def upsert_csv(path: Path, df_new: pd.DataFrame):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = pd.read_csv(path, dtype=str)
        merged = pd.concat([old, df_new.astype(str)], ignore_index=True)
        merged = merged.drop_duplicates(subset=['trade_date'], keep='last').sort_values('trade_date')
    else:
        merged = df_new.astype(str).sort_values('trade_date')
    merged.to_csv(path, index=False, encoding='utf-8-sig')


def main():
    ts.set_token(TOKEN)
    pro = ts.pro_api()
    stock_basic = pd.read_csv(ROOT / 'data' / 'meta' / 'stock_basic.csv', dtype=str).fillna('')
    stock_basic = stock_basic[~stock_basic['ts_code'].astype(str).str.endswith('.BJ')]
    codes = stock_basic['ts_code'].dropna().astype(str).unique().tolist()
    total = len(codes)

    processed = START_PROCESSED
    ok = START_PROCESSED
    fail = 0

    save('running', processed, ok, fail, f'resuming tail from index {START_PROCESSED}')

    for code in codes[START_PROCESSED:]:
        try:
            daily = pro.daily(ts_code=code, trade_date=TRADE_DATE)
            if daily is not None and not daily.empty:
                upsert_csv(ROOT / 'data' / 'daily' / f'{code}.csv', daily)
            adj = pro.adj_factor(ts_code=code, trade_date=TRADE_DATE)
            if adj is not None and not adj.empty:
                upsert_csv(ROOT / 'data' / 'adj_factor' / f'{code}.csv', adj)
            basic = pro.daily_basic(ts_code=code, trade_date=TRADE_DATE)
            if basic is not None and not basic.empty:
                upsert_csv(ROOT / 'data' / 'daily_basic' / f'{code}.csv', basic)
            ok += 1
        except Exception:
            fail += 1
        processed += 1
        if processed % 20 == 0 or processed == total:
            save('running', processed, ok, fail, f'tail progress {processed}/{total}')
        if SLEEP_SEC > 0:
            time.sleep(SLEEP_SEC)

    save('done', processed, ok, fail, 'tail resume finished')
    print(OUT)


if __name__ == '__main__':
    main()
