#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quant.indicators import add_tactic_base_indicators

START_DATE='20230101'
END_DATE='20260401'
PROGRESS_PATH = ROOT / 'outputs' / 'b1_v2_daily_weekly_resonance_backtest_progress.json'
RESULT_PATH = ROOT / 'outputs' / 'b1_v2_daily_weekly_resonance_backtest.json'
EVENTS_PATH = ROOT / 'outputs' / 'b1_v2_daily_weekly_resonance_backtest_events.csv'


def save_progress(status,total,done):
    pct=round(done/total*100,2) if total else 100.0
    PROGRESS_PATH.write_text(json.dumps({'task':'b1_v2_daily_weekly_resonance_backtest','status':status,'updated_at':time.strftime('%Y-%m-%d %H:%M:%S'),'total_codes':total,'completed_codes':done,'progress_pct':pct}, ensure_ascii=False, indent=2), encoding='utf-8')


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


def b1_v2_ok(df, idx, is_weekly=False):
    td=str(df.iloc[idx]['trade_date'])
    high=pd.to_numeric(df.iloc[idx]['high'], errors='coerce'); white=pd.to_numeric(df.iloc[idx]['white_line'], errors='coerce'); yellow=pd.to_numeric(df.iloc[idx]['yellow_line'], errors='coerce'); jv=pd.to_numeric(df.iloc[idx]['kdj_j'], errors='coerce'); mv=pd.to_numeric(df.iloc[idx]['total_mv_billion'], errors='coerce')
    base=((pd.notna(jv) and jv < j_threshold(td)) and (pd.notna(mv) and mv > 100) and (pd.notna(white) and pd.notna(yellow) and white > yellow) and (pd.notna(high) and pd.notna(white) and high >= white))
    if not base: return False
    start=max(0, idx-20); sub=df.iloc[start:idx+1].copy().reset_index(drop=True)
    if len(sub) < 8: return False
    close=pd.to_numeric(sub['close'], errors='coerce'); peak_idx=close.idxmax()
    if peak_idx >= len(sub)-1: return False
    pullback_len=len(sub)-1-peak_idx
    max_len = 8 if is_weekly else 15
    if pullback_len > max_len: return False
    peak=float(close.iloc[peak_idx]); cur=float(close.iloc[-1])
    if peak<=0 or (peak-cur)/peak*100 > 15: return False
    pb=sub.iloc[peak_idx+1:].copy(); red = pd.to_numeric(pb['close'], errors='coerce') < pd.to_numeric(pb['open'], errors='coerce'); red_pb=pb[red].copy()
    if len(red_pb) < 2 or 'vol' not in red_pb.columns: return False
    red_vol=pd.to_numeric(red_pb['vol'], errors='coerce').dropna().tolist()
    if len(red_vol) < 2: return False
    mid=max(1, len(red_vol)//2); first=red_vol[:mid]; second=red_vol[mid:]
    return bool(second) and (sum(second)/len(second) < sum(first)/len(first))


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


def resample_weekly(df):
    d=df.copy()
    d['date']=pd.to_datetime(d['trade_date'])
    d=d.sort_values('date')
    d['week']=d['date'].dt.to_period('W-FRI').astype(str)
    agg=d.groupby('week').agg(
        trade_date=('trade_date','last'),
        open=('open','first'),
        high=('high','max'),
        low=('low','min'),
        close=('close','last'),
        vol=('vol','sum') if 'vol' in d.columns else ('close','size'),
        total_mv_billion=('total_mv_billion','last')
    ).reset_index(drop=True)
    return agg


def main():
    omav = pd.read_csv(ROOT/'data'/'omav'/'omav_daily_standardized_20260402.csv', dtype={'trade_date':str})
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
        if not p.exists() or not pb.exists(): done+=1; continue
        try:
            df=pd.read_csv(p, dtype={'trade_date':str}); db=pd.read_csv(pb, dtype={'trade_date':str})
            if df.empty or len(df)<260 or not {'trade_date','open','high','low','close'}.issubset(df.columns): done+=1; continue
            db=db[['trade_date','total_mv']].copy() if 'total_mv' in db.columns else pd.DataFrame(columns=['trade_date','total_mv'])
            db['total_mv_billion']=pd.to_numeric(db['total_mv'], errors='coerce')/10000.0
            df=df.sort_values('trade_date').reset_index(drop=True).merge(db[['trade_date','total_mv_billion']], on='trade_date', how='left')
            df=add_tactic_base_indicators(df); df=add_kdj(df); df=add_bbi(df)
            df=df[(df['trade_date']>=START_DATE)&(df['trade_date']<=END_DATE)].reset_index(drop=True)
            wdf=resample_weekly(df)
            wdf=add_tactic_base_indicators(wdf); wdf=add_kdj(wdf); wdf=add_bbi(wdf)
            weekly_ok_dates=set()
            for wi in range(len(wdf)):
                if b1_v2_ok(wdf, wi, is_weekly=True):
                    weekly_ok_dates.add(str(wdf.iloc[wi]['trade_date']))
            # expand weekly signal to daily dates within that weekly bar up to bar date
            weekly_resonance_dates=set()
            if weekly_ok_dates:
                for td in df['trade_date'].astype(str):
                    week_bar = wdf[wdf['trade_date']>=td].head(1)
                    if not week_bar.empty and str(week_bar.iloc[0]['trade_date']) in weekly_ok_dates:
                        weekly_resonance_dates.add(td)
            for idx in range(len(df)):
                td=str(df.iloc[idx]['trade_date'])
                if td not in weekly_resonance_dates: continue
                if not b1_v2_ok(df, idx, is_weekly=False): continue
                env=omav_map.get(td)
                if not env: continue
                action_weight=1.0
                if bool(env['omav_rotation_warning_flag']): action_weight*=0.5
                if bool(env['omav_bear_regime_flag']): action_weight*=0.5
                trade=simulate_trade(df, idx)
                if not trade: continue
                trade.update({'signal_date':td,'code':row.ts_code,'name':row.name,'industry':row.industry,'omav':float(env['omav']) if env['omav']!='' else None,'action_weight':action_weight})
                events.append(trade)
        except Exception:
            pass
        done+=1
        if done%100==0 or done==total: save_progress('running', total, done)
    events_df=pd.DataFrame(events)
    events_df.to_csv(EVENTS_PATH, index=False, encoding='utf-8-sig')
    result={'strategy':'b1_v2_daily_weekly_resonance','date_range':[START_DATE,END_DATE],'summary':summarize(events_df),'events_path':str(EVENTS_PATH),'definition':'周线B1战法V2 + 日线B1战法V2 同时满足'}
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save_progress('completed', total, total)
    print(RESULT_PATH)

if __name__ == '__main__':
    main()
