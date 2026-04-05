from pathlib import Path
import time
import pandas as pd
import tushare as ts

ROOT = Path('/Users/alimars/.openclaw/workspace/quant-trading')
DATA = ROOT / 'data'
TRADE_DATE = '20260323'
TOKEN = 'be0e395aeb600a02110bcac4fca37a8d5b792afe8f13507040357d23'

ts.set_token(TOKEN)
pro = ts.pro_api()

TARGET_CODES = [
    '000049.SZ', '000045.SZ', '000423.SZ', '001872.SZ', '000722.SZ', '000429.SZ',
    '000539.SZ', '603986.SH', '000001.SH'
]


def normalize_trade_date(df: pd.DataFrame):
    if df is None or df.empty:
        return df
    out = df.copy()
    if 'trade_date' in out.columns:
        out['trade_date'] = out['trade_date'].astype(str)
    if 'ts_code' in out.columns:
        out['ts_code'] = out['ts_code'].astype(str)
    return out


def upsert_csv(path: Path, new_df: pd.DataFrame, sort_col='trade_date'):
    new_df = normalize_trade_date(new_df)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = pd.read_csv(path, dtype=str)
        old = normalize_trade_date(old)
        df = pd.concat([old, new_df], ignore_index=True)
        subset = ['ts_code', sort_col] if 'ts_code' in df.columns else [sort_col]
        df = df.drop_duplicates(subset=subset, keep='last')
    else:
        df = new_df.copy()
    if sort_col in df.columns:
        df = df.sort_values(sort_col).reset_index(drop=True)
    df.to_csv(path, index=False)


def fetch_and_write(code: str):
    result = {'code': code}
    daily = pro.daily(ts_code=code, trade_date=TRADE_DATE)
    if daily is not None and not daily.empty:
        upsert_csv(DATA / 'daily' / f'{code}.csv', daily)
        result['daily'] = 'ok'
    else:
        result['daily'] = 'empty'

    if code != '000001.SH':
        daily_basic = pro.daily_basic(ts_code=code, trade_date=TRADE_DATE)
        if daily_basic is not None and not daily_basic.empty:
            upsert_csv(DATA / 'daily_basic' / f'{code}.csv', daily_basic)
            result['daily_basic'] = 'ok'
        else:
            result['daily_basic'] = 'empty'

        adj = pro.adj_factor(ts_code=code, trade_date=TRADE_DATE)
        if adj is not None and not adj.empty:
            upsert_csv(DATA / 'adj_factor' / f'{code}.csv', adj)
            result['adj_factor'] = 'ok'
        else:
            result['adj_factor'] = 'empty'

        mf = pro.moneyflow(ts_code=code, trade_date=TRADE_DATE)
        if mf is not None and not mf.empty:
            upsert_csv(DATA / 'moneyflow' / f'{code}.csv', mf)
            result['moneyflow'] = 'ok'
        else:
            result['moneyflow'] = 'empty'

        try:
            md = pro.margin_detail(ts_code=code, trade_date=TRADE_DATE)
            if md is not None and not md.empty:
                upsert_csv(DATA / 'margin_detail' / f'{code}.csv', md)
                result['margin_detail'] = 'ok'
            else:
                result['margin_detail'] = 'empty'
        except Exception as e:
            result['margin_detail'] = f'skip:{e}'
    else:
        idx = pro.index_daily(ts_code=code, trade_date=TRADE_DATE)
        if idx is not None and not idx.empty:
            upsert_csv(DATA / 'index_daily' / f'{code}.csv', idx)
            result['index_daily'] = 'ok'
        else:
            result['index_daily'] = 'empty'
    return result


if __name__ == '__main__':
    all_results = []
    for i, code in enumerate(TARGET_CODES, start=1):
        try:
            r = fetch_and_write(code)
            all_results.append(r)
            print(r)
        except Exception as e:
            print({'code': code, 'error': str(e)})
        time.sleep(0.25)
    print({'status': 'done', 'trade_date': TRADE_DATE, 'count': len(TARGET_CODES)})
