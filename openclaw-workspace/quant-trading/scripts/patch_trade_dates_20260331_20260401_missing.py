#!/usr/bin/env python3
import json, time
from pathlib import Path
import pandas as pd
import tushare as ts

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'patch_20260331_20260401_missing_progress.json'
TOKEN = 'be0e395aeb600a02110bcac4fca37a8d5b792afe8f13507040357d23'
DATES = ['20260331','20260401']
BATCH_SIZE = 180
SLEEP_SEC = 65


def save(status, processed=0, ok=0, fail=0, missing_targets=0, message=''):
    OUT.write_text(json.dumps({
        'task': 'patch_trade_dates_20260331_20260401_missing',
        'dates': DATES,
        'status': status,
        'processed': processed,
        'ok': ok,
        'fail': fail,
        'missing_targets': missing_targets,
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


def has_trade_date(path: Path, td: str) -> bool:
    if not path.exists():
        return False
    try:
        df = pd.read_csv(path, usecols=['trade_date'], dtype={'trade_date': str})
        return td in set(df['trade_date'])
    except Exception:
        return False


def main():
    save('running', message='starting')
    ts.set_token(TOKEN)
    pro = ts.pro_api()
    meta = pd.read_csv(ROOT / 'data' / 'meta' / 'stock_basic.csv', dtype=str).fillna('')
    meta = meta[~meta['ts_code'].astype(str).str.endswith('.BJ')]
    codes = meta['ts_code'].astype(str).unique().tolist()

    targets = []
    for code in codes:
        p = ROOT / 'data' / 'daily' / f'{code}.csv'
        need = [td for td in DATES if not has_trade_date(p, td)]
        if need:
            targets.append((code, need))

    processed = ok = fail = 0
    total = len(targets)
    save('running', processed, ok, fail, total, f'targets={total}')

    for start in range(0, total, BATCH_SIZE):
        batch = targets[start:start+BATCH_SIZE]
        for code, need_dates in batch:
            try:
                for td in need_dates:
                    daily = pro.daily(ts_code=code, trade_date=td)
                    if daily is not None and not daily.empty:
                        upsert_csv(ROOT / 'data' / 'daily' / f'{code}.csv', daily)
                    adj = pro.adj_factor(ts_code=code, trade_date=td)
                    if adj is not None and not adj.empty:
                        upsert_csv(ROOT / 'data' / 'adj_factor' / f'{code}.csv', adj)
                    basic = pro.daily_basic(ts_code=code, trade_date=td)
                    if basic is not None and not basic.empty:
                        upsert_csv(ROOT / 'data' / 'daily_basic' / f'{code}.csv', basic)
                ok += 1
            except Exception:
                fail += 1
            processed += 1
            if processed % 20 == 0 or processed == total:
                save('running', processed, ok, fail, total, f'progress {processed}/{total}')
        if start + BATCH_SIZE < total:
            save('running', processed, ok, fail, total, f'sleeping after batch ending {processed}')
            time.sleep(SLEEP_SEC)

    save('done', processed, ok, fail, total, 'finished')
    print(OUT)

if __name__ == '__main__':
    main()
