import json
import time
from pathlib import Path
import pandas as pd
import tushare as ts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / 'data'
OUTPUT_ROOT = PROJECT_ROOT / 'outputs'
PROGRESS_PATH = OUTPUT_ROOT / 'patch_20260401_full_progress.json'
TRADE_DATE = '20260401'
BATCH_SIZE = 200
SLEEP_SEC = 0.25

TOKEN = 'be0e395aeb600a02110bcac4fca37a8d5b792afe8f13507040357d23'
ts.set_token(TOKEN)
pro = ts.pro_api()


def ensure_dirs():
    for name in ['daily', 'daily_basic', 'adj_factor', 'moneyflow']:
        (DATA_ROOT / name).mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def upsert_csv(path: Path, new_df: pd.DataFrame):
    if new_df is None or new_df.empty:
        return
    new_df = new_df.copy()
    if 'trade_date' in new_df.columns:
        new_df['trade_date'] = new_df['trade_date'].astype(str)
    if path.exists():
        old = pd.read_csv(path)
        if 'trade_date' in old.columns:
            old['trade_date'] = old['trade_date'].astype(str)
        merged = pd.concat([old, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=['ts_code', 'trade_date'], keep='last')
    else:
        merged = new_df
    if 'trade_date' in merged.columns:
        merged = merged.sort_values('trade_date')
    merged.to_csv(path, index=False)


def save_progress(obj):
    PROGRESS_PATH.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def load_universe():
    stock_basic = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name,industry,market')
    stock_basic['ts_code'] = stock_basic['ts_code'].astype(str)
    stock_basic = stock_basic[~stock_basic['name'].astype(str).str.contains('ST', case=False, na=False)]
    stock_basic = stock_basic[~stock_basic['market'].astype(str).isin(['北交所'])]
    stock_basic = stock_basic[~stock_basic['ts_code'].astype(str).str.endswith('.BJ')]
    stock_basic = stock_basic[~stock_basic['ts_code'].astype(str).str.startswith(('300','301'))]
    stock_basic = stock_basic[~stock_basic['industry'].astype(str).str.contains('房地产', na=False)]
    return stock_basic[['ts_code', 'name', 'industry']].drop_duplicates().reset_index(drop=True)


def fetch_one(dataset, code):
    if dataset == 'daily':
        return pro.daily(ts_code=code, trade_date=TRADE_DATE)
    if dataset == 'daily_basic':
        return pro.daily_basic(ts_code=code, trade_date=TRADE_DATE)
    if dataset == 'adj_factor':
        return pro.adj_factor(ts_code=code, trade_date=TRADE_DATE)
    if dataset == 'moneyflow':
        return pro.moneyflow(ts_code=code, trade_date=TRADE_DATE)
    raise ValueError(dataset)


def main():
    ensure_dirs()
    universe = load_universe()
    total = len(universe)
    if PROGRESS_PATH.exists():
        progress = json.loads(PROGRESS_PATH.read_text(encoding='utf-8'))
        progress['status'] = 'running'
        progress.setdefault('datasets', ['daily', 'daily_basic', 'adj_factor', 'moneyflow'])
        progress.setdefault('started_at', time.strftime('%Y-%m-%d %H:%M:%S'))
    else:
        progress = {
            'status': 'running',
            'trade_date': TRADE_DATE,
            'processed': 0,
            'total': total,
            'ok': 0,
            'fail': 0,
            'batch_size': BATCH_SIZE,
            'last_code': None,
            'datasets': ['daily', 'daily_basic', 'adj_factor', 'moneyflow'],
            'started_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }
    save_progress(progress)

    start_idx = int(progress.get('processed', 0))
    for idx, row in universe.iloc[start_idx:].iterrows():
        code = row['ts_code']
        try:
            for dataset in progress['datasets']:
                df = fetch_one(dataset, code)
                if df is not None and not df.empty:
                    upsert_csv(DATA_ROOT / dataset / f'{code}.csv', df)
            progress['ok'] += 1
        except Exception:
            progress['fail'] += 1
        progress['processed'] = idx + 1
        progress['last_code'] = code
        if (idx + 1) % BATCH_SIZE == 0 or (idx + 1) == total:
            save_progress(progress)
        time.sleep(SLEEP_SEC)

    progress['status'] = 'done'
    progress['finished_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    save_progress(progress)
    print(json.dumps(progress, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
