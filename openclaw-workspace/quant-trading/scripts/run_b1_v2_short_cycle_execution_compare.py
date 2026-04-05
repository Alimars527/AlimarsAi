#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quant.indicators import add_tactic_base_indicators

START_DATE='20230101'
END_DATE='20260401'
PROGRESS_PATH = ROOT / 'outputs' / 'b1_v2_short_cycle_execution_compare_progress.json'
RESULT_PATH = ROOT / 'outputs' / 'b1_v2_short_cycle_execution_compare.json'
EVENTS_PATH = ROOT / 'outputs' / 'b1_v2_short_cycle_execution_compare_events.csv'


def save_progress(status,total,done):
    pct=round(done/total*100,2) if total else 100.0
    PROGRESS_PATH.write_text(json.dumps({'task':'b1_v2_short_cycle_execution_compare','status':status,'updated_at':time.strftime('%Y-%m-%d %H:%M:%S'),'total_codes':total,'completed_codes':done,'progress_pct':pct}, ensure_ascii=False, indent=2), encoding='utf-8')


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
    core=arr[k:n-k] if 2*k < n else arr
    return round(sum(core)/len(core), 4) if core else 0.0


def summarize(series):
    s=pd.to_numeric(series, errors='coerce').dropna()
    if s.empty:
        return {'count':0,'win_rate':0,'avg_return':0,'median':0,'trimmed_mean_10':0,'trimmed_mean_20':0}
    return {'count':int(len(s)),'win_rate':round((s>0).mean()*100,2),'avg_return':round(s.mean(),4),'median':round(s.median(),4),'trimmed_mean_10':trimmed_mean(s.tolist(),0.10),'trimmed_mean_20':trimmed_mean(s.tolist(),0.20)}


def exit_fixed(df, idx, hold_days):
    entry_i=idx+1
    if entry_i >= len(df) or idx+hold_days >= len(df): return None
    entry=float(df.iloc[entry_i]['open']); exit_px=float(df.iloc[idx+hold_days]['close'])
    return (exit_px/entry-1)*100 if entry>0 else None


def exit_takeprofit_stoploss(df, idx, tp_pct, sl_pct, max_days=4):
    entry_i=idx+1
    if entry_i >= len(df): return None
    entry=float(df.iloc[entry_i]['open'])
    if entry<=0: return None
    end=min(len(df)-1, idx+max_days)
    for j in range(entry_i, end+1):
        high=float(df.iloc[j]['high']); low=float(df.iloc[j]['low']); close=float(df.iloc[j]['close'])
        tp=entry*(1+tp_pct/100); sl=entry*(1+sl_pct/100)
        hit_tp = high >= tp
        hit_sl = low <= sl
        if hit_tp and hit_sl:
            # conservative: stop first
            return (sl/entry-1)*100
        if hit_sl:
            return (sl/entry-1)*100
        if hit_tp:
            return (tp/entry-1)*100
    close_end=float(df.iloc[end]['close'])
    return (close_end/entry-1)*100


def exit_close_weak(df, idx, max_days=4):
    entry_i=idx+1
    if entry_i >= len(df): return None
    entry=float(df.iloc[entry_i]['open'])
    if entry<=0: return None
    end=min(len(df)-1, idx+max_days)
    for j in range(entry_i+1, end+1):
        close_j=float(df.iloc[j]['close']); close_prev=float(df.iloc[j-1]['close'])
        if close_j < close_prev:
            return (close_j/entry-1)*100
    close_end=float(df.iloc[end]['close'])
    return (close_end/entry-1)*100


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
            for idx in range(len(df)-6):
                if not b1_v2_ok(df, idx):
                    continue
                rec={'code':row.ts_code,'name':row.name,'industry':row.industry,'signal_date':str(df.iloc[idx]['trade_date'])}
                rec['fixed_2d']=exit_fixed(df, idx, 2)
                rec['fixed_3d']=exit_fixed(df, idx, 3)
                rec['fixed_4d']=exit_fixed(df, idx, 4)
                rec['tp3_sl3_4d']=exit_takeprofit_stoploss(df, idx, 3, -3, 4)
                rec['tp4_sl3_4d']=exit_takeprofit_stoploss(df, idx, 4, -3, 4)
                rec['tp5_sl3_4d']=exit_takeprofit_stoploss(df, idx, 5, -3, 4)
                rec['tp4_sl2_4d']=exit_takeprofit_stoploss(df, idx, 4, -2, 4)
                rec['close_weak_4d']=exit_close_weak(df, idx, 4)
                rows.append(rec)
        except Exception:
            pass
        done+=1
        if done%100==0 or done==total:
            save_progress('running', total, done)
    events=pd.DataFrame(rows)
    events.to_csv(EVENTS_PATH, index=False, encoding='utf-8-sig')
    result={'strategy':'b1_v2_short_cycle_execution_compare','date_range':[START_DATE,END_DATE],'signal_count':int(len(events)),'variants':{},'events_path':str(EVENTS_PATH)}
    for col in ['fixed_2d','fixed_3d','fixed_4d','tp3_sl3_4d','tp4_sl3_4d','tp5_sl3_4d','tp4_sl2_4d','close_weak_4d']:
        result['variants'][col]=summarize(events[col]) if not events.empty else summarize(pd.Series(dtype=float))
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save_progress('completed', total, total)
    print(RESULT_PATH)

if __name__ == '__main__':
    main()
