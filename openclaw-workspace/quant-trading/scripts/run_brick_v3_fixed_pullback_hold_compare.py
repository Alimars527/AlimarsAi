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
PROGRESS_PATH = ROOT / 'outputs' / 'brick_v3_fixed_pullback_hold_compare_progress.json'
RESULT_PATH = ROOT / 'outputs' / 'brick_v3_fixed_pullback_hold_compare.json'
EVENTS_PATH = ROOT / 'outputs' / 'brick_v3_fixed_pullback_hold_compare_events.csv'


def save_progress(status,total,done):
    pct=round(done/total*100,2) if total else 100.0
    PROGRESS_PATH.write_text(json.dumps({'task':'brick_v3_fixed_pullback_hold_compare','status':status,'updated_at':time.strftime('%Y-%m-%d %H:%M:%S'),'total_codes':total,'completed_codes':done,'progress_pct':pct}, ensure_ascii=False, indent=2), encoding='utf-8')


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
    rows=[]
    for row in meta[['ts_code','name','industry']].itertuples(index=False):
        p=ROOT/'data'/'daily'/f'{row.ts_code}.csv'
        if not p.exists():
            done+=1; continue
        try:
            df=pd.read_csv(p, dtype={'trade_date':str}).sort_values('trade_date').reset_index(drop=True)
            if df.empty or len(df)<260 or not {'trade_date','open','high','low','close'}.issubset(df.columns):
                done+=1; continue
            df=add_tactic_base_indicators(df)
            df=add_brick_formula_flags(df)
            df=df[(df['trade_date']>=START_DATE)&(df['trade_date']<=END_DATE)].reset_index(drop=True)
            for idx in range(len(df)-4):
                if not brick_v3_ok(df, idx, row.industry, rotation_map, omav_map):
                    continue
                c0=float(df.iloc[idx]['close']); o1=float(df.iloc[idx+1]['open']); l1=float(df.iloc[idx+1]['low'])
                entry=min(c0*0.995, o1*0.99)
                filled = l1 <= entry
                if not filled:
                    continue
                rec={'signal_date':str(df.iloc[idx]['trade_date']),'code':row.ts_code,'name':row.name,'industry':row.industry,'entry_price':entry}
                for n in [1,2,3]:
                    close_n=float(df.iloc[idx+n]['close'])
                    rec[f'hold_{n}d']=(close_n/entry-1)*100 if entry>0 else None
                rows.append(rec)
        except Exception:
            pass
        done+=1
        if done%100==0 or done==total:
            save_progress('running', total, done)
    events=pd.DataFrame(rows)
    events.to_csv(EVENTS_PATH, index=False, encoding='utf-8-sig')
    result={'strategy':'brick_v3_fixed_pullback_hold_compare','date_range':[START_DATE,END_DATE],'signal_count':int(len(events)),'entry_formula':'min(signal_close*0.995, next_open*0.99)','variants':{
        'hold_1d': summarize(events['hold_1d']) if not events.empty else summarize(pd.Series(dtype=float)),
        'hold_2d': summarize(events['hold_2d']) if not events.empty else summarize(pd.Series(dtype=float)),
        'hold_3d': summarize(events['hold_3d']) if not events.empty else summarize(pd.Series(dtype=float)),
    },'events_path':str(EVENTS_PATH)}
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save_progress('completed', total, total)
    print(RESULT_PATH)

if __name__ == '__main__':
    main()
