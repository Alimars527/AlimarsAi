#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quant.indicators import add_tactic_base_indicators

START_DATE='20230101'
END_DATE='20260401'
PROGRESS_PATH = ROOT / 'outputs' / 'b1_rebuild_v1_constrained_bc_compare_progress.json'
RESULT_PATH = ROOT / 'outputs' / 'b1_rebuild_v1_constrained_bc_compare.json'
EVENTS_PATH = ROOT / 'outputs' / 'b1_rebuild_v1_constrained_bc_compare_events.csv'


def save_progress(status,total,done):
    pct=round(done/total*100,2) if total else 100.0
    PROGRESS_PATH.write_text(json.dumps({'task':'b1_rebuild_v1_constrained_bc_compare','status':status,'updated_at':time.strftime('%Y-%m-%d %H:%M:%S'),'total_codes':total,'completed_codes':done,'progress_pct':pct}, ensure_ascii=False, indent=2), encoding='utf-8')


def add_kdj(df):
    out=df.copy()
    h=pd.to_numeric(out['high'], errors='coerce'); l=pd.to_numeric(out['low'], errors='coerce'); c=pd.to_numeric(out['close'], errors='coerce')
    low9=l.rolling(9).min(); high9=h.rolling(9).max(); rsv=(c-low9)/(high9-low9).replace(0, pd.NA)*100
    out['kdj_k']=rsv.ewm(alpha=1/3, adjust=False).mean(); out['kdj_d']=out['kdj_k'].ewm(alpha=1/3, adjust=False).mean(); out['kdj_j']=3*out['kdj_k']-2*out['kdj_d']
    return out


def add_bbi(df):
    out=df.copy(); c=pd.to_numeric(out['close'], errors='coerce')
    out['bbi']=(c.rolling(3).mean()+c.rolling(6).mean()+c.rolling(12).mean()+c.rolling(24).mean())/4
    return out


def j_threshold(td):
    y=str(td)[:4]
    return {'2023':-10,'2024':0,'2025':18}.get(y,25)


def simulate_trade(df, idx):
    if idx+1 >= len(df): return None
    entry_i=idx+1; entry=float(df.iloc[entry_i]['open'])
    if pd.isna(entry) or entry<=0: return None
    break_days=0; exit_i=None; reason='end_of_data'
    for j in range(entry_i, len(df)):
        row=df.iloc[j]; o=float(row['open']); c=float(row['close']); body=abs(c-o); is_green=c<o
        if j>entry_i:
            prev=df.iloc[j-1]; po=float(prev['open']); pc=float(prev['close']); prev_red_body=abs(pc-po) if pc>po else None
            if is_green and prev_red_body and prev_red_body>0:
                ratio=body/prev_red_body
                if 0.65 <= ratio <= 0.85:
                    exit_i=j; reason='three_quarter_green_body_takeprofit'; break
        bbi=pd.to_numeric(row['bbi'], errors='coerce')
        if pd.notna(bbi) and c < bbi: break_days += 1
        else: break_days = 0
        if break_days >= 2:
            exit_i=j; reason='break_bbi_2days'; break
    if exit_i is None: exit_i=len(df)-1
    exit=float(df.iloc[exit_i]['close'])
    return {'entry_date':str(df.iloc[entry_i]['trade_date']),'exit_date':str(df.iloc[exit_i]['trade_date']),'return_pct':(exit/entry-1)*100,'exit_reason':reason}


def summarize(df):
    if df.empty: return {'event_count':0,'signal_days':0,'win_rate':0,'avg_return_pct':0,'median_return_pct':0}
    ret=pd.to_numeric(df['return_pct'], errors='coerce')
    return {'event_count':int(len(df)),'signal_days':int(df['signal_date'].nunique()),'win_rate':round((ret>0).mean()*100,2),'avg_return_pct':round(ret.mean(),4),'median_return_pct':round(ret.median(),4)}


def constraint_flags(df, idx):
    start=max(0, idx-20)
    sub=df.iloc[start:idx+1].copy().reset_index(drop=True)
    if len(sub) < 8:
        return False, False, False
    close=pd.to_numeric(sub['close'], errors='coerce'); open_=pd.to_numeric(sub['open'], errors='coerce'); vol=pd.to_numeric(sub.get('vol', pd.Series([None]*len(sub))), errors='coerce')
    peak_idx=close.idxmax()
    if peak_idx >= len(sub)-1: return False, False, False
    pullback_len=len(sub)-1-peak_idx
    if pullback_len > 15: return False, False, False
    peak=float(close.iloc[peak_idx]); cur=float(close.iloc[-1])
    if peak<=0 or (peak-cur)/peak*100 > 15: return False, False, False
    pb=sub.iloc[peak_idx+1:].copy()
    if pb.empty: return False, False, False
    red = pd.to_numeric(pb['close'], errors='coerce') < pd.to_numeric(pb['open'], errors='coerce')
    red_pb = pb[red].copy()
    # B: second-half avg green(red-day) volume < first-half avg
    b_ok=False
    if len(red_pb) >= 2 and 'vol' in red_pb.columns:
        red_vol = pd.to_numeric(red_pb['vol'], errors='coerce').dropna().tolist()
        if len(red_vol) >= 2:
            mid=max(1, len(red_vol)//2)
            first=red_vol[:mid]; second=red_vol[mid:]
            if second and sum(second)/len(second) < sum(first)/len(first):
                b_ok=True
    # C: latest green(red-day) volume <= previous max green(red-day) volume
    c_ok=False
    if len(red_pb) >= 2 and 'vol' in red_pb.columns:
        red_vol = pd.to_numeric(red_pb['vol'], errors='coerce').dropna().tolist()
        if len(red_vol) >= 2 and red_vol[-1] <= max(red_vol[:-1]):
            c_ok=True
    base_ok=True
    return base_ok, b_ok, c_ok


def main():
    omav = pd.read_csv(ROOT / 'data' / 'omav' / 'omav_daily_standardized_20260402.csv', dtype={'trade_date':str})
    omav = omav[(omav['trade_date']>=START_DATE)&(omav['trade_date']<=END_DATE)].copy()
    omav['omav_rotation_warning_flag']=omav['omav_rotation_warning_flag'].astype(str).str.lower().eq('true')
    omav['omav_bear_regime_flag']=omav['omav_bear_regime_flag'].astype(str).str.lower().eq('true')
    omav_map=omav.set_index('trade_date')[['omav','omav_rotation_warning_flag','omav_bear_regime_flag']].to_dict('index')
    meta=pd.read_csv(ROOT/'data'/'meta'/'stock_basic.csv', dtype=str).fillna('')
    meta=meta[~meta['ts_code'].astype(str).str.endswith('.BJ')]
    meta=meta[~meta['name'].astype(str).str.contains('ST', case=False, na=False)]
    meta=meta[~meta['industry'].astype(str).isin(['银行'])]
    meta=meta[~meta['industry'].astype(str).str.contains('房地产', na=False)]
    total=len(meta); done=0; save_progress('running', total, 0)
    events=[]
    for row in meta[['ts_code','name','industry']].itertuples(index=False):
        p=ROOT/'data'/'daily'/f'{row.ts_code}.csv'; pb=ROOT/'data'/'daily_basic'/f'{row.ts_code}.csv'
        if not p.exists() or not pb.exists(): done += 1; continue
        try:
            df=pd.read_csv(p, dtype={'trade_date':str}); db=pd.read_csv(pb, dtype={'trade_date':str})
            if df.empty or len(df)<260 or not {'trade_date','open','high','low','close'}.issubset(df.columns): done += 1; continue
            db=db[['trade_date','total_mv']].copy() if 'total_mv' in db.columns else pd.DataFrame(columns=['trade_date','total_mv'])
            db['total_mv_billion']=pd.to_numeric(db['total_mv'], errors='coerce')/10000.0
            df=df.sort_values('trade_date').reset_index(drop=True).merge(db[['trade_date','total_mv_billion']], on='trade_date', how='left')
            df=add_tactic_base_indicators(df); df=add_kdj(df); df=add_bbi(df)
            df=df[(df['trade_date']>=START_DATE)&(df['trade_date']<=END_DATE)].reset_index(drop=True)
            high=pd.to_numeric(df['high'], errors='coerce'); white=pd.to_numeric(df['white_line'], errors='coerce'); yellow=pd.to_numeric(df['yellow_line'], errors='coerce'); jv=pd.to_numeric(df['kdj_j'], errors='coerce'); mv=pd.to_numeric(df['total_mv_billion'], errors='coerce')
            for idx, td in enumerate(df['trade_date'].astype(str)):
                base=((pd.notna(jv.iloc[idx]) and jv.iloc[idx] < j_threshold(td)) and (pd.notna(mv.iloc[idx]) and mv.iloc[idx] > 100) and (pd.notna(white.iloc[idx]) and pd.notna(yellow.iloc[idx]) and white.iloc[idx] > yellow.iloc[idx]) and (pd.notna(high.iloc[idx]) and pd.notna(white.iloc[idx]) and high.iloc[idx] >= white.iloc[idx]))
                if not base: continue
                _, b_ok, c_ok = constraint_flags(df, idx)
                if not (b_ok or c_ok):
                    continue
                env=omav_map.get(td)
                if not env: continue
                action_weight=1.0
                if bool(env['omav_rotation_warning_flag']): action_weight*=0.5
                if bool(env['omav_bear_regime_flag']): action_weight*=0.5
                trade=simulate_trade(df, idx)
                if not trade: continue
                mode='B+C' if (b_ok and c_ok) else ('B' if b_ok else 'C')
                trade.update({'signal_date':td,'code':row.ts_code,'name':row.name,'industry':row.industry,'mode':mode,'b_ok':b_ok,'c_ok':c_ok,'omav':float(env['omav']) if env['omav']!='' else None,'action_weight':action_weight})
                events.append(trade)
        except Exception:
            pass
        done += 1
        if done % 100 == 0 or done == total: save_progress('running', total, done)
    events_df=pd.DataFrame(events)
    events_df.to_csv(EVENTS_PATH, index=False, encoding='utf-8-sig')
    result={'strategy':'b1_rebuild_v1_constrained_bc_compare','date_range':[START_DATE,END_DATE],'overall':summarize(events_df),'B_only':summarize(events_df[events_df['mode']=='B']) if not events_df.empty else summarize(pd.DataFrame()),'C_only':summarize(events_df[events_df['mode']=='C']) if not events_df.empty else summarize(pd.DataFrame()),'B_and_C':summarize(events_df[events_df['mode']=='B+C']) if not events_df.empty else summarize(pd.DataFrame()),'events_path':str(EVENTS_PATH),'note':'仅保留回调<=15%、时间<=15天；量能收束用方式B/C比较；OMAV作为权重层'}
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save_progress('completed', total, total)
    print(RESULT_PATH)

if __name__ == '__main__':
    main()
