#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quant.indicators import add_tactic_base_indicators

START_DATE = '20230101'
END_DATE = '20260403'
PROGRESS_PATH = ROOT / 'outputs' / 'b1_taskB_round2_refine_progress.json'
SUMMARY_PATH = ROOT / 'outputs' / 'b1_taskB_round2_refine_summary.json'
COMPARE_PATH = ROOT / 'outputs' / 'b1_taskB_round2_refine_compare.csv'
YEARLY_PATH = ROOT / 'outputs' / 'b1_taskB_round2_refine_yearly.csv'
TAIL_PATH = ROOT / 'outputs' / 'b1_taskB_round2_refine_tail_risk.csv'
EVENTS_PATH = ROOT / 'outputs' / 'b1_taskB_round2_refine_events.csv'

VARIANTS = {
    'B1_BASE_NEW': {'desc': '新本体：去掉回调幅度<=15%', 'need': {'j_threshold', 'mv_100', 'white_over_yellow', 'not_full_under_white'}},
    'B1_BASE_NEW_PLUS_DAYS': {'desc': '新本体 + 回调时间<=15天', 'need': {'j_threshold', 'mv_100', 'white_over_yellow', 'not_full_under_white', 'pullback_days'}},
    'B1_BASE_NEW_PLUS_VOLUME': {'desc': '新本体 + 量能收束B', 'need': {'j_threshold', 'mv_100', 'white_over_yellow', 'not_full_under_white', 'volume_shrink_b'}},
    'B1_BASE_NEW_PLUS_DAYS_VOLUME': {'desc': '新本体 + 回调时间<=15天 + 量能收束B', 'need': {'j_threshold', 'mv_100', 'white_over_yellow', 'not_full_under_white', 'pullback_days', 'volume_shrink_b'}},
}


def save_progress(status, total, done, message=''):
    pct = round(done / total * 100, 2) if total else 100.0
    PROGRESS_PATH.write_text(json.dumps({'task':'b1_taskB_round2_refine','status':status,'updated_at':time.strftime('%Y-%m-%d %H:%M:%S'),'total_codes':total,'completed_codes':done,'progress_pct':pct,'message':message}, ensure_ascii=False, indent=2), encoding='utf-8')


def j_threshold(td: str) -> float:
    y = td[:4]
    if y == '2023': return -10
    if y == '2024': return 0
    if y == '2025': return 18
    return 25


def trimmed_mean(vals, trim_ratio):
    arr = sorted([float(x) for x in vals if pd.notna(x)])
    n = len(arr)
    if n == 0:
        return 0.0
    k = int(n * trim_ratio)
    core = arr[k:n-k] if 2*k < n else arr
    return round(sum(core) / len(core), 4) if core else 0.0


def summarize_series(series: pd.Series):
    s = pd.to_numeric(series, errors='coerce').dropna()
    if s.empty:
        return {'event_count':0,'win_rate':0.0,'avg_return':0.0,'median_return':0.0,'trimmed_mean_10':0.0,'trimmed_mean_20':0.0,'max_loss':0.0,'worst_5pct_mean':0.0}
    q5 = s.quantile(0.05)
    tail = s[s <= q5]
    return {
        'event_count': int(len(s)),
        'win_rate': round((s > 0).mean() * 100, 2),
        'avg_return': round(s.mean(), 4),
        'median_return': round(s.median(), 4),
        'trimmed_mean_10': trimmed_mean(s.tolist(), 0.10),
        'trimmed_mean_20': trimmed_mean(s.tolist(), 0.20),
        'max_loss': round(s.min(), 4),
        'worst_5pct_mean': round(tail.mean(), 4) if not tail.empty else 0.0,
    }


def add_bbi(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = pd.to_numeric(out['close'], errors='coerce')
    out['bbi'] = (c.rolling(3).mean() + c.rolling(6).mean() + c.rolling(12).mean() + c.rolling(24).mean()) / 4
    return out


def build_condition_flags(df: pd.DataFrame, idx: int):
    row = df.iloc[idx]
    td = str(row['trade_date'])
    high = pd.to_numeric(row.get('high'), errors='coerce')
    white = pd.to_numeric(row.get('white_line'), errors='coerce')
    yellow = pd.to_numeric(row.get('yellow_line'), errors='coerce')
    jv = pd.to_numeric(row.get('kdj_j'), errors='coerce')
    mv = pd.to_numeric(row.get('total_mv_billion'), errors='coerce')
    flags = {
        'j_threshold': pd.notna(jv) and jv < j_threshold(td),
        'mv_100': pd.notna(mv) and mv > 100,
        'white_over_yellow': pd.notna(white) and pd.notna(yellow) and white > yellow,
        'not_full_under_white': pd.notna(high) and pd.notna(white) and high >= white,
    }
    start = max(0, idx - 20)
    sub = df.iloc[start:idx+1].copy().reset_index(drop=True)
    close = pd.to_numeric(sub['close'], errors='coerce')
    if len(sub) < 8 or close.dropna().empty:
        flags['pullback_days'] = False
        flags['volume_shrink_b'] = False
        return flags
    peak_idx = close.idxmax()
    if peak_idx >= len(sub) - 1:
        flags['pullback_days'] = False
        flags['volume_shrink_b'] = False
        return flags
    pullback_len = len(sub) - 1 - peak_idx
    flags['pullback_days'] = pullback_len <= 15
    pb = sub.iloc[peak_idx+1:].copy()
    red = pd.to_numeric(pb['close'], errors='coerce') < pd.to_numeric(pb['open'], errors='coerce')
    red_pb = pb[red].copy()
    volume_ok = False
    if len(red_pb) >= 2 and 'vol' in red_pb.columns:
        red_vol = pd.to_numeric(red_pb['vol'], errors='coerce').dropna().tolist()
        if len(red_vol) >= 2:
            mid = max(1, len(red_vol) // 2)
            first = red_vol[:mid]; second = red_vol[mid:]
            volume_ok = bool(second) and (sum(second) / len(second) < sum(first) / len(first))
    flags['volume_shrink_b'] = volume_ok
    return flags


def simulate_trade(df, idx):
    if idx + 3 >= len(df):
        return None
    signal_close = float(pd.to_numeric(df.iloc[idx]['close'], errors='coerce'))
    next_open = float(pd.to_numeric(df.iloc[idx+1]['open'], errors='coerce'))
    next_low = float(pd.to_numeric(df.iloc[idx+1]['low'], errors='coerce'))
    entry = min(signal_close * 0.993, next_open * 0.988)
    if next_low > entry or entry <= 0:
        return None
    exit_close = float(pd.to_numeric(df.iloc[idx+3]['close'], errors='coerce'))
    ret = (exit_close / entry - 1) * 100
    return {'entry_date': str(df.iloc[idx+1]['trade_date']), 'exit_date': str(df.iloc[idx+3]['trade_date']), 'entry_price': round(entry, 4), 'exit_price': round(exit_close, 4), 'return_pct': round(ret, 4)}


def main():
    meta = pd.read_csv(ROOT / 'data' / 'meta' / 'stock_basic.csv', dtype=str).fillna('')
    meta = meta[~meta['ts_code'].astype(str).str.endswith('.BJ')]
    meta = meta[~meta['name'].astype(str).str.contains('ST', case=False, na=False)]
    meta = meta[~meta['industry'].astype(str).isin(['银行'])]
    meta = meta[~meta['industry'].astype(str).str.contains('房地产', na=False)]
    total = len(meta)
    done = 0
    save_progress('running', total, 0, 'start')
    events = []
    for row in meta[['ts_code', 'name', 'industry']].itertuples(index=False):
        p = ROOT / 'data' / 'daily' / f'{row.ts_code}.csv'
        pb = ROOT / 'data' / 'daily_basic' / f'{row.ts_code}.csv'
        if not p.exists() or not pb.exists():
            done += 1; continue
        try:
            df = pd.read_csv(p, dtype={'trade_date': str}).sort_values('trade_date').reset_index(drop=True)
            db = pd.read_csv(pb, dtype={'trade_date': str})
            if df.empty or len(df) < 260 or not {'trade_date','open','high','low','close','vol'}.issubset(df.columns):
                done += 1; continue
            if 'total_mv' in db.columns:
                db = db[['trade_date','total_mv']].copy()
                db['total_mv_billion'] = pd.to_numeric(db['total_mv'], errors='coerce') / 10000.0
                df = df.merge(db[['trade_date','total_mv_billion']], on='trade_date', how='left')
            else:
                df['total_mv_billion'] = pd.NA
            df = add_tactic_base_indicators(df)
            df = add_bbi(df)
            df = df[(df['trade_date'] >= START_DATE) & (df['trade_date'] <= END_DATE)].reset_index(drop=True)
            for idx in range(len(df) - 3):
                flags = build_condition_flags(df, idx)
                for variant_name, conf in VARIANTS.items():
                    if not all(flags.get(k, False) for k in conf['need']):
                        continue
                    trade = simulate_trade(df, idx)
                    if not trade:
                        continue
                    events.append({'variant': variant_name, 'variant_desc': conf['desc'], 'signal_date': str(df.iloc[idx]['trade_date']), 'year': str(df.iloc[idx]['trade_date'])[:4], 'code': row.ts_code, 'name': row.name, 'industry': row.industry, **trade})
        except Exception:
            pass
        done += 1
        if done % 100 == 0 or done == total:
            save_progress('running', total, done, f'processed {done}/{total}')
    events_df = pd.DataFrame(events)
    events_df.to_csv(EVENTS_PATH, index=False, encoding='utf-8-sig')
    compare_rows=[]; yearly_rows=[]; tail_rows=[]
    summary={'task':'Task B Round2 - B1精简复核','date_range':[START_DATE, END_DATE],'variants':{}}
    for variant_name, conf in VARIANTS.items():
        sub = events_df[events_df['variant'] == variant_name].copy() if not events_df.empty else pd.DataFrame()
        s = summarize_series(sub['return_pct'] if not sub.empty else pd.Series(dtype=float))
        s['signal_days'] = int(sub['signal_date'].nunique()) if not sub.empty else 0
        s['variant_desc'] = conf['desc']
        summary['variants'][variant_name] = s
        compare_rows.append({'variant': variant_name, 'variant_desc': conf['desc'], **s})
        if not sub.empty:
            for year, ydf in sub.groupby('year'):
                ys = summarize_series(ydf['return_pct'])
                yearly_rows.append({'variant': variant_name, 'year': year, **ys, 'signal_days': int(ydf['signal_date'].nunique())})
            worst10 = sub.sort_values('return_pct', ascending=True).head(10)
            tail_rows.append({'variant': variant_name, 'worst_trade': round(float(worst10['return_pct'].min()),4), 'worst_10_avg': round(float(worst10['return_pct'].mean()),4), 'worst_5pct_mean': s['worst_5pct_mean']})
        else:
            tail_rows.append({'variant': variant_name, 'worst_trade': 0.0, 'worst_10_avg': 0.0, 'worst_5pct_mean': 0.0})
    pd.DataFrame(compare_rows).to_csv(COMPARE_PATH, index=False, encoding='utf-8-sig')
    pd.DataFrame(yearly_rows).to_csv(YEARLY_PATH, index=False, encoding='utf-8-sig')
    pd.DataFrame(tail_rows).to_csv(TAIL_PATH, index=False, encoding='utf-8-sig')
    summary.update({'compare_path': str(COMPARE_PATH), 'yearly_path': str(YEARLY_PATH), 'tail_risk_path': str(TAIL_PATH), 'events_path': str(EVENTS_PATH)})
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    save_progress('completed', total, total, 'done')
    print(SUMMARY_PATH)

if __name__ == '__main__':
    main()
