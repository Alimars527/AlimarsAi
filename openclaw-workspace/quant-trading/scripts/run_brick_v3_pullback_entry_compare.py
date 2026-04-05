#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quant.indicators import add_tactic_base_indicators
from quant.brick_formula import add_brick_formula_flags

START_DATE='20230101'
END_DATE='20260401'
PROGRESS_PATH = ROOT / 'outputs' / 'brick_v3_pullback_entry_compare_progress.json'
RESULT_PATH = ROOT / 'outputs' / 'brick_v3_pullback_entry_compare.json'
EVENTS_PATH = ROOT / 'outputs' / 'brick_v3_pullback_entry_compare_events.csv'

CONFIGS = [
    ('min_c0995_o099', 0.995, 0.99, 'min'),
    ('min_c099_o0985', 0.99, 0.985, 'min'),
    ('min_c0985_o098', 0.985, 0.98, 'min'),
    ('close_only_099', 0.99, None, 'close_only'),
    ('open_only_0985', None, 0.985, 'open_only'),
]


def save_progress(status,total,done):
    pct=round(done/total*100,2) if total else 100.0
    PROGRESS_PATH.write_text(json.dumps({'task':'brick_v3_pullback_entry_compare','status':status,'updated_at':time.strftime('%Y-%m-%d %H:%M:%S'),'total_codes':total,'completed_codes':done,'progress_pct':pct}, ensure_ascii=False, indent=2), encoding='utf-8')


def trimmed_mean(vals, trim_ratio):
    arr=sorted([float(x) for x in vals if pd.notna(x)])
    n=len(arr)
    if n==0: return 0.0
    k=int(n*trim_ratio)
    core=arr[k:n-k] if 2*k < n else arr
    return round(sum(core)/len(core), 4) if core else 0.0


def summarize(series):
    s=pd.to_numeric(series, errors='coerce').dropna()
    if s.empty:
        return {'count':0,'win_rate':0,'avg_return':0,'median':0,'trimmed_mean_10':0,'trimmed_mean_20':0}
    return {'count':int(len(s)),'win_rate':round((s>0).mean()*100,2),'avg_return':round(s.mean(),4),'median':round(s.median(),4),'trimmed_mean_10':trimmed_mean(s.tolist(),0.10),'trimmed_mean_20':trimmed_mean(s.tolist(),0.20)}


def build_rotation_top5_map(meta):
    rows=[]
    for row in meta[['ts_code','industry']].itertuples(index=False):
        p=ROOT/'data'/'daily'/f'{row.ts_code}.csv'
        if not p.exists() or not row.industry: continue
        try:
            df=pd.read_csv(p, usecols=['trade_date','pct_chg'], dtype={'trade_date':str})
            df=df[(df['trade_date']>=START_DATE)&(df['trade_date']<=END_DATE)].copy()
            if df.empty: continue
            df['pct_chg']=pd.to_numeric(df['pct_chg'], errors='coerce'); df['industry']=row.industry
            rows.append(df[['trade_date','industry','pct_chg']])
        except Exception:
            continue
    if not rows: return {}
    ind=pd.concat(rows, ignore_index=True)
    board=ind.groupby(['trade_date','industry'], as_index=False)['pct_chg'].mean().sort_values(['trade_date','pct_chg'], ascending=[True,False])
    board['rank']=board.groupby('trade_date')['pct_chg'].rank(method='first', ascending=False)
    return board[board['rank']<=5].assign(flag=True).set_index(['trade_date','industry'])['flag'].to_dict()


def brick_v3_ok(df, idx, industry, rotation_map, omav_map):
    td=str(df.iloc[idx]['trade_date'])
    env=omav_map.get(td)
    if not env: return False
    if bool(env['omav_rotation_warning_flag']) or bool(env['omav_bear_regime_flag']): return False
    if not rotation_map.get((td, industry), False): return False
    z = pd.to_numeric(df['brick_formula_value'], errors='coerce').fillna(0)
    green = df['brick_formula_green'].fillna(False).astype(bool)
    xg = df['brick_raw_turn_red'].fillna(False).astype(bool)
    white = pd.to_numeric(df['white_line'], errors='coerce')
    yellow = pd.to_numeric(df['yellow_line'], errors='coerce')
    high = pd.to_numeric(df['high'], errors='coerce')
    return bool(idx>=4 and xg.iloc[idx] and bool(df['brick_history_ok'].fillna(False).astype(bool).iloc[idx]) and high.iloc[idx]>=white.iloc[idx] and white.iloc[idx]>yellow.iloc[idx] and green.iloc[idx-1] and green.iloc[idx-2] and green.iloc[idx-3] and green.iloc[idx-4] and (z.iloc[idx-4] > z.iloc[idx-3] > z.iloc[idx-2] > z.iloc[idx-1]) and (z.iloc[idx] >= z.iloc[idx-1]))


def main():
    meta=pd.read_csv(ROOT/'data'/'meta'/'stock_basic.csv', dtype=str).fillna('')
    meta=meta[~meta['ts_code'].astype(str).str.endswith('.BJ')]
    meta=meta[~meta['name'].astype(str).str.contains('ST', case=False, na=False)]
    meta=meta[~meta['industry'].astype(str).isin(['银行'])]
    meta=meta[~meta['industry'].astype(str).str.contains('房地产', na=False)]

    omav = pd.read_csv(ROOT/'data'/'omav'/'omav_daily_standardized_20260402.csv', dtype={'trade_date':str})
    omav = omav[(omav['trade_date']>=START_DATE)&(omav['trade_date']<=END_DATE)].copy()
    omav['omav_rotation_warning_flag']=omav['omav_rotation_warning_flag'].astype(str).str.lower().eq('true')
    omav['omav_bear_regime_flag']=omav['omav_bear_regime_flag'].astype(str).str.lower().eq('true')
    omav_map=omav.set_index('trade_date')[['omav_rotation_warning_flag','omav_bear_regime_flag']].to_dict('index')
    rotation_map=build_rotation_top5_map(meta)

    total=len(meta); done=0; save_progress('running', total, 0)
    rows=[]; signal_count=0; signal_days=set()
    for row in meta[['ts_code','name','industry']].itertuples(index=False):
        p=ROOT/'data'/'daily'/f'{row.ts_code}.csv'
        if not p.exists():
            done += 1; continue
        try:
            df=pd.read_csv(p, dtype={'trade_date':str}).sort_values('trade_date').reset_index(drop=True)
            if df.empty or len(df)<260 or not {'trade_date','open','high','low','close'}.issubset(df.columns):
                done += 1; continue
            df=add_tactic_base_indicators(df)
            df=add_brick_formula_flags(df)
            df=df[(df['trade_date']>=START_DATE)&(df['trade_date']<=END_DATE)].reset_index(drop=True)
            for idx in range(len(df)-5):
                if not brick_v3_ok(df, idx, row.industry, rotation_map, omav_map):
                    continue
                signal_count += 1
                signal_days.add(str(df.iloc[idx]['trade_date']))
                c0=float(df.iloc[idx]['close']); o1=float(df.iloc[idx+1]['open']); l1=float(df.iloc[idx+1]['low']); c3=float(df.iloc[idx+3]['close'])
                for name, c_coef, o_coef, mode in CONFIGS:
                    if mode=='min':
                        entry=min(c0*c_coef, o1*o_coef)
                    elif mode=='close_only':
                        entry=c0*c_coef
                    else:
                        entry=o1*o_coef
                    filled = l1 <= entry
                    ret = (c3/entry-1)*100 if filled and entry>0 else None
                    rows.append({'signal_date':str(df.iloc[idx]['trade_date']),'code':row.ts_code,'name':row.name,'industry':row.industry,'variant':name,'entry_price':entry,'filled':filled,'return_3d':ret})
        except Exception:
            pass
        done += 1
        if done % 100 == 0 or done == total:
            save_progress('running', total, done)
    events=pd.DataFrame(rows)
    events.to_csv(EVENTS_PATH, index=False, encoding='utf-8-sig')
    out={'strategy':'brick_v3_pullback_entry_compare','date_range':[START_DATE,END_DATE],'signal_count':signal_count,'signal_days':len(signal_days),'variants':{},'events_path':str(EVENTS_PATH)}
    if not events.empty:
        for name, *_ in CONFIGS:
            sub=events[events['variant']==name].copy()
            filled=sub[sub['filled']==True].copy()
            fill_count=int(len(filled))
            fill_days=int(filled['signal_date'].nunique()) if not filled.empty else 0
            out['variants'][name]={
                'fill_count': fill_count,
                'fill_days': fill_days,
                'fill_rate_pct': round(fill_count/max(signal_count,1)*100,2),
                'fill_day_rate_pct': round(fill_days/max(len(signal_days),1)*100,2),
                'avg_symbols_per_fill_day': round(fill_count/max(fill_days,1),2) if fill_days else 0,
                'return_3d': summarize(filled['return_3d']) if not filled.empty else summarize(pd.Series(dtype=float))
            }
    RESULT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    save_progress('completed', total, total)
    print(RESULT_PATH)

if __name__ == '__main__':
    main()
