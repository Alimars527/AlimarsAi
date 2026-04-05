#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quant.indicators import add_tactic_base_indicators

START_DATE='20230101'
END_DATE='20260401'
PROGRESS_PATH = ROOT / 'outputs' / 'b1_v2_execution_layer_review_progress.json'
RESULT_PATH = ROOT / 'outputs' / 'b1_v2_execution_layer_review.json'
EVENTS_PATH = ROOT / 'outputs' / 'b1_v2_execution_layer_review_events.csv'


def save_progress(status,total,done):
    pct=round(done/total*100,2) if total else 100.0
    PROGRESS_PATH.write_text(json.dumps({'task':'b1_v2_execution_layer_review','status':status,'updated_at':time.strftime('%Y-%m-%d %H:%M:%S'),'total_codes':total,'completed_codes':done,'progress_pct':pct}, ensure_ascii=False, indent=2), encoding='utf-8')


def add_kdj(df):
    out=df.copy(); h=pd.to_numeric(out['high'], errors='coerce'); l=pd.to_numeric(out['low'], errors='coerce'); c=pd.to_numeric(out['close'], errors='coerce')
    low9=l.rolling(9).min(); high9=h.rolling(9).max(); rsv=(c-low9)/(high9-low9).replace(0, pd.NA)*100
    out['kdj_k']=rsv.ewm(alpha=1/3, adjust=False).mean(); out['kdj_d']=out['kdj_k'].ewm(alpha=1/3, adjust=False).mean(); out['kdj_j']=3*out['kdj_k']-2*out['kdj_d']
    return out


def add_bbi(df):
    out=df.copy(); c=pd.to_numeric(out['close'], errors='coerce')
    out['bbi']=(c.rolling(3).mean()+c.rolling(6).mean()+c.rolling(12).mean()+c.rolling(24).mean())/4
    return out


def j_threshold(td):
    return {'2023':-10,'2024':0,'2025':18}.get(str(td)[:4],25)


def b1_v2_ok(df, idx):
    td=str(df.iloc[idx]['trade_date'])
    high=pd.to_numeric(df.iloc[idx]['high'], errors='coerce'); white=pd.to_numeric(df.iloc[idx]['white_line'], errors='coerce'); yellow=pd.to_numeric(df.iloc[idx]['yellow_line'], errors='coerce'); jv=pd.to_numeric(df.iloc[idx]['kdj_j'], errors='coerce'); mv=pd.to_numeric(df.iloc[idx]['total_mv_billion'], errors='coerce')
    base=((pd.notna(jv) and jv < j_threshold(td)) and (pd.notna(mv) and mv > 100) and (pd.notna(white) and pd.notna(yellow) and white > yellow) and (pd.notna(high) and pd.notna(white) and high >= white))
    if not base: return False
    start=max(0, idx-20); sub=df.iloc[start:idx+1].copy().reset_index(drop=True)
    if len(sub) < 8: return False
    close=pd.to_numeric(sub['close'], errors='coerce'); peak_idx=close.idxmax()
    if peak_idx >= len(sub)-1: return False
    pullback_len=len(sub)-1-peak_idx
    if pullback_len > 15: return False
    peak=float(close.iloc[peak_idx]); cur=float(close.iloc[-1])
    if peak<=0 or (peak-cur)/peak*100 > 15: return False
    pb=sub.iloc[peak_idx+1:].copy(); red = pd.to_numeric(pb['close'], errors='coerce') < pd.to_numeric(pb['open'], errors='coerce'); red_pb=pb[red].copy()
    if len(red_pb) < 2 or 'vol' not in red_pb.columns: return False
    red_vol=pd.to_numeric(red_pb['vol'], errors='coerce').dropna().tolist()
    if len(red_vol) < 2: return False
    mid=max(1, len(red_vol)//2); first=red_vol[:mid]; second=red_vol[mid:]
    return bool(second) and (sum(second)/len(second) < sum(first)/len(first))


def trimmed_mean(vals, trim_ratio):
    arr=sorted([float(x) for x in vals if pd.notna(x)])
    n=len(arr)
    if n==0: return 0.0
    k=int(n*trim_ratio)
    if 2*k >= n:
        core=arr
    else:
        core=arr[k:n-k]
    return round(sum(core)/len(core), 4) if core else 0.0


def summarize_returns(series):
    s=pd.to_numeric(series, errors='coerce').dropna()
    if s.empty:
        return {'count':0,'win_rate':0,'avg_return':0,'median':0,'trimmed_mean_10':0,'trimmed_mean_20':0}
    return {
        'count': int(len(s)),
        'win_rate': round((s>0).mean()*100,2),
        'avg_return': round(s.mean(),4),
        'median': round(s.median(),4),
        'trimmed_mean_10': trimmed_mean(s.tolist(), 0.10),
        'trimmed_mean_20': trimmed_mean(s.tolist(), 0.20),
    }


def main():
    meta=pd.read_csv(ROOT/'data'/'meta'/'stock_basic.csv', dtype=str).fillna('')
    meta=meta[~meta['ts_code'].astype(str).str.endswith('.BJ')]
    meta=meta[~meta['name'].astype(str).str.contains('ST', case=False, na=False)]
    meta=meta[~meta['industry'].astype(str).isin(['银行'])]
    meta=meta[~meta['industry'].astype(str).str.contains('房地产', na=False)]
    total=len(meta); done=0; save_progress('running', total, 0)
    rows=[]
    for row in meta[['ts_code','name','industry']].itertuples(index=False):
        p=ROOT/'data'/'daily'/f'{row.ts_code}.csv'; pb=ROOT/'data'/'daily_basic'/f'{row.ts_code}.csv'
        if not p.exists() or not pb.exists(): done+=1; continue
        try:
            df=pd.read_csv(p, dtype={'trade_date':str}); db=pd.read_csv(pb, dtype={'trade_date':str})
            if df.empty or len(df)<260 or not {'trade_date','open','high','low','close'}.issubset(df.columns): done+=1; continue
            db=db[['trade_date','total_mv']].copy() if 'total_mv' in db.columns else pd.DataFrame(columns=['trade_date','total_mv'])
            db['total_mv_billion']=pd.to_numeric(db['total_mv'], errors='coerce')/10000.0
            df=df.sort_values('trade_date').reset_index(drop=True).merge(db[['trade_date','total_mv_billion']], on='trade_date', how='left')
            df=add_tactic_base_indicators(df); df=add_kdj(df); df=add_bbi(df)
            df=df[(df['trade_date']>=START_DATE)&(df['trade_date']<=END_DATE)].reset_index(drop=True)
            for idx in range(len(df)-11):
                if not b1_v2_ok(df, idx):
                    continue
                sig=df.iloc[idx]
                o1=float(df.iloc[idx+1]['open']); c0=float(df.iloc[idx]['close'])
                rec={'code':row.ts_code,'name':row.name,'industry':row.industry,'signal_date':str(sig['trade_date'])}
                # natural forward behavior from next-day open baseline
                for n in [1,3,5,10]:
                    close_n=float(df.iloc[idx+n]['close'])
                    high_max=float(pd.to_numeric(df.iloc[idx+1:idx+n+1]['high'], errors='coerce').max())
                    low_min=float(pd.to_numeric(df.iloc[idx+1:idx+n+1]['low'], errors='coerce').min())
                    rec[f'open_entry_hold_{n}d']= (close_n/o1-1)*100 if o1>0 else None
                    rec[f'open_entry_maxgain_{n}d']= (high_max/o1-1)*100 if o1>0 else None
                    rec[f'open_entry_maxdd_{n}d']= (low_min/o1-1)*100 if o1>0 else None
                # compare different simple entries for 5d hold
                c1=float(df.iloc[idx+1]['close']); l1=float(df.iloc[idx+1]['low'])
                c5=float(df.iloc[idx+5]['close'])
                rec['entry_signal_close_hold_5d']=(c5/c0-1)*100 if c0>0 else None
                rec['entry_next_open_hold_5d']=(c5/o1-1)*100 if o1>0 else None
                rec['entry_next_close_hold_5d']=(c5/c1-1)*100 if c1>0 else None
                rec['entry_next_low_hold_5d']=(c5/l1-1)*100 if l1>0 else None
                # current execution proxies
                # fixed holds from next open
                for n in [3,5,10]:
                    rec[f'fixed_hold_{n}d'] = rec[f'open_entry_hold_{n}d']
                # bbi stop 2d from next open
                entry=o1; break_days=0; exit_ret=None
                for j in range(idx+1, min(len(df), idx+11)):
                    close_j=float(df.iloc[j]['close']); bbi=pd.to_numeric(df.iloc[j]['bbi'], errors='coerce')
                    if pd.notna(bbi) and close_j < bbi: break_days += 1
                    else: break_days = 0
                    if break_days >= 2:
                        exit_ret=(close_j/entry-1)*100 if entry>0 else None
                        break
                if exit_ret is None:
                    close10=float(df.iloc[idx+10]['close']); exit_ret=(close10/entry-1)*100 if entry>0 else None
                rec['exit_bbi_2days_or_10d']=exit_ret
                rows.append(rec)
        except Exception:
            pass
        done+=1
        if done%100==0 or done==total:
            save_progress('running', total, done)
    events=pd.DataFrame(rows)
    events.to_csv(EVENTS_PATH, index=False, encoding='utf-8-sig')
    result={
        'strategy':'b1_v2_execution_layer_review',
        'date_range':[START_DATE,END_DATE],
        'signal_count': int(len(events)),
        'signal_quality': {
            'open_entry_hold_1d': summarize_returns(events['open_entry_hold_1d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
            'open_entry_hold_3d': summarize_returns(events['open_entry_hold_3d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
            'open_entry_hold_5d': summarize_returns(events['open_entry_hold_5d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
            'open_entry_hold_10d': summarize_returns(events['open_entry_hold_10d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
            'open_entry_maxgain_5d': summarize_returns(events['open_entry_maxgain_5d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
            'open_entry_maxgain_10d': summarize_returns(events['open_entry_maxgain_10d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
            'open_entry_maxdd_5d': summarize_returns(events['open_entry_maxdd_5d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
        },
        'entry_compare_5d_hold': {
            'signal_close': summarize_returns(events['entry_signal_close_hold_5d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
            'next_open': summarize_returns(events['entry_next_open_hold_5d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
            'next_close': summarize_returns(events['entry_next_close_hold_5d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
            'next_low_proxy': summarize_returns(events['entry_next_low_hold_5d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
        },
        'exit_compare_from_next_open': {
            'fixed_hold_3d': summarize_returns(events['fixed_hold_3d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
            'fixed_hold_5d': summarize_returns(events['fixed_hold_5d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
            'fixed_hold_10d': summarize_returns(events['fixed_hold_10d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
            'bbi_2days_or_10d': summarize_returns(events['exit_bbi_2days_or_10d']) if not events.empty else summarize_returns(pd.Series(dtype=float)),
        },
        'events_path': str(EVENTS_PATH)
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save_progress('completed', total, total)
    print(RESULT_PATH)

if __name__ == '__main__':
    main()
