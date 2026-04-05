#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quant.indicators import add_tactic_base_indicators

START_DATE='20230101'
END_DATE='20260401'
PROGRESS_PATH = ROOT / 'outputs' / 'b1_rebuild_v1_constrained_backtest_progress.json'
RESULT_PATH = ROOT / 'outputs' / 'b1_rebuild_v1_constrained_backtest.json'
EVENTS_PATH = ROOT / 'outputs' / 'b1_rebuild_v1_constrained_backtest_events.csv'
ANNUAL_PATH = ROOT / 'outputs' / 'b1_rebuild_v1_constrained_backtest_annual.csv'
MONTHLY_PATH = ROOT / 'outputs' / 'b1_rebuild_v1_constrained_backtest_monthly.csv'


def save_progress(status,total,done):
    pct=round(done/total*100,2) if total else 100.0
    PROGRESS_PATH.write_text(json.dumps({'task':'b1_rebuild_v1_constrained_backtest','status':status,'updated_at':time.strftime('%Y-%m-%d %H:%M:%S'),'total_codes':total,'completed_codes':done,'progress_pct':pct,'start_date':START_DATE,'end_date':END_DATE}, ensure_ascii=False, indent=2), encoding='utf-8')


def add_kdj(df):
    out=df.copy()
    high=pd.to_numeric(out['high'], errors='coerce')
    low=pd.to_numeric(out['low'], errors='coerce')
    close=pd.to_numeric(out['close'], errors='coerce')
    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()
    rsv = (close - low9) / (high9 - low9).replace(0, pd.NA) * 100
    out['kdj_k'] = rsv.ewm(alpha=1/3, adjust=False).mean()
    out['kdj_d'] = out['kdj_k'].ewm(alpha=1/3, adjust=False).mean()
    out['kdj_j'] = 3 * out['kdj_k'] - 2 * out['kdj_d']
    return out


def add_bbi(df):
    out=df.copy()
    close=pd.to_numeric(out['close'], errors='coerce')
    out['bbi'] = (close.rolling(3).mean() + close.rolling(6).mean() + close.rolling(12).mean() + close.rolling(24).mean()) / 4
    return out


def get_j_threshold(trade_date):
    y=str(trade_date)[:4]
    if y == '2023': return -10
    if y == '2024': return 0
    if y == '2025': return 18
    return 25


def simulate_trade(df, idx):
    if idx + 1 >= len(df): return None
    entry_i = idx + 1
    entry_price = float(df.iloc[entry_i]['open'])
    if pd.isna(entry_price) or entry_price <= 0: return None
    break_line_days = 0
    exit_i = None; exit_reason = 'end_of_data'
    for j in range(entry_i, len(df)):
        row=df.iloc[j]
        open_px=float(row['open']); close_px=float(row['close'])
        body=abs(close_px-open_px)
        is_green=close_px < open_px
        if j > entry_i:
            prev=df.iloc[j-1]
            prev_open=float(prev['open']); prev_close=float(prev['close'])
            prev_red_body=abs(prev_close-prev_open) if prev_close > prev_open else None
            if is_green and prev_red_body and prev_red_body > 0:
                ratio=body/prev_red_body
                if 0.65 <= ratio <= 0.85:
                    exit_i=j; exit_reason='three_quarter_green_body_takeprofit'; break
        ref_line = pd.to_numeric(row['bbi'], errors='coerce')
        if pd.notna(ref_line) and close_px < ref_line:
            break_line_days += 1
        else:
            break_line_days = 0
        if break_line_days >= 2:
            exit_i=j; exit_reason='break_bbi_2days'; break
    if exit_i is None: exit_i = len(df)-1
    exit_price=float(df.iloc[exit_i]['close'])
    return {'entry_date':str(df.iloc[entry_i]['trade_date']),'exit_date':str(df.iloc[exit_i]['trade_date']),'entry_price':entry_price,'exit_price':exit_price,'return_pct':(exit_price/entry_price-1)*100,'holding_days':int(exit_i-entry_i+1),'exit_reason':exit_reason}


def summarize(df, group_col=None):
    if df.empty:
        if group_col:
            return pd.DataFrame(columns=[group_col,'event_count','signal_days','win_rate','avg_return_pct','median_return_pct'])
        return {'event_count':0,'signal_days':0,'win_rate':0,'avg_return_pct':0,'median_return_pct':0}
    if group_col is None:
        ret=pd.to_numeric(df['return_pct'], errors='coerce')
        return {'event_count':int(len(df)),'signal_days':int(df['signal_date'].nunique()),'win_rate':round((ret>0).mean()*100,2),'avg_return_pct':round(ret.mean(),4),'median_return_pct':round(ret.median(),4)}
    g=df.groupby(group_col)
    return g.agg(event_count=('code','count'),signal_days=('signal_date','nunique'),win_rate=('return_pct', lambda s: round((pd.to_numeric(s, errors='coerce')>0).mean()*100,2)),avg_return_pct=('return_pct', lambda s: round(pd.to_numeric(s, errors='coerce').mean(),4)),median_return_pct=('return_pct', lambda s: round(pd.to_numeric(s, errors='coerce').median(),4))).reset_index()


def constrained_ok(df, idx):
    # lookback window for pullback structure
    start=max(0, idx-20)
    sub=df.iloc[start:idx+1].copy().reset_index(drop=True)
    if len(sub) < 8:
        return False
    close=pd.to_numeric(sub['close'], errors='coerce')
    open_=pd.to_numeric(sub['open'], errors='coerce')
    high=pd.to_numeric(sub['high'], errors='coerce')
    vol=pd.to_numeric(sub.get('vol', pd.Series([None]*len(sub))), errors='coerce')

    # define latest peak before signal within 15 bars
    peak_local_idx = close.idxmax()
    if peak_local_idx >= len(sub)-1:
        return False
    pullback_len = len(sub)-1 - peak_local_idx
    if pullback_len > 15:
        return False
    peak_close = float(close.iloc[peak_local_idx])
    curr_close = float(close.iloc[-1])
    if peak_close <= 0:
        return False
    drawdown_pct = (peak_close - curr_close) / peak_close * 100
    if drawdown_pct > 15:
        return False

    # no gap-up in rise phase before pullback
    rise = sub.iloc[:peak_local_idx+1].copy()
    if len(rise) >= 2:
        prev_high = pd.to_numeric(rise['high'].shift(1), errors='coerce')
        curr_low = pd.to_numeric(rise['low'], errors='coerce')
        gap_up = (curr_low > prev_high).fillna(False)
        if bool(gap_up.iloc[1:].any()):
            return False

    # pullback phase stats
    pb = sub.iloc[peak_local_idx+1:].copy()
    if pb.empty:
        return False
    # no more than 2 big down candles with volume expansion
    prev_vol = pd.to_numeric(pb.get('vol', pd.Series([None]*len(pb))).shift(1), errors='coerce')
    red = pd.to_numeric(pb['close'], errors='coerce') < pd.to_numeric(pb['open'], errors='coerce')
    body = (pd.to_numeric(pb['open'], errors='coerce') - pd.to_numeric(pb['close'], errors='coerce')).clip(lower=0)
    big_red = red & ((body / pd.to_numeric(pb['close'], errors='coerce').replace(0, pd.NA)) >= 0.03)
    vol_expand = (pd.to_numeric(pb.get('vol', pd.Series([None]*len(pb))), errors='coerce') > prev_vol).fillna(False)
    if int((big_red & vol_expand).sum()) > 1:
        return False

    # shrinking green volume bars: use red-day volume non-increasing overall
    red_pb = pb[red].copy()
    if len(red_pb) >= 2 and 'vol' in red_pb.columns:
        red_vol = pd.to_numeric(red_pb['vol'], errors='coerce').dropna().tolist()
        if len(red_vol) >= 2:
            nonincreasing = all(red_vol[i] <= red_vol[i-1] for i in range(1, len(red_vol)))
            if not nonincreasing:
                return False
    return True


def main():
    omav = pd.read_csv(ROOT / 'data' / 'omav' / 'omav_daily_standardized_20260402.csv', dtype={'trade_date':str})
    omav = omav[(omav['trade_date']>=START_DATE) & (omav['trade_date']<=END_DATE)].copy()
    omav['omav_rotation_warning_flag'] = omav['omav_rotation_warning_flag'].astype(str).str.lower().eq('true')
    omav['omav_bear_regime_flag'] = omav['omav_bear_regime_flag'].astype(str).str.lower().eq('true')
    omav_map = omav.set_index('trade_date')[['omav','omav_bullish_flag','omav_rotation_warning_flag','omav_bear_regime_flag']].to_dict('index')

    meta = pd.read_csv(ROOT / 'data' / 'meta' / 'stock_basic.csv', dtype=str).fillna('')
    meta = meta[~meta['ts_code'].astype(str).str.endswith('.BJ')]
    meta = meta[~meta['name'].astype(str).str.contains('ST', case=False, na=False)]
    meta = meta[~meta['industry'].astype(str).isin(['银行'])]
    meta = meta[~meta['industry'].astype(str).str.contains('房地产', na=False)]

    total=len(meta); done=0; save_progress('running', total, 0)
    events=[]
    for row in meta[['ts_code','name','industry']].itertuples(index=False):
        p=ROOT/'data'/'daily'/f'{row.ts_code}.csv'
        pb=ROOT/'data'/'daily_basic'/f'{row.ts_code}.csv'
        if not p.exists() or not pb.exists():
            done += 1; continue
        try:
            df = pd.read_csv(p, dtype={'trade_date':str})
            need_cols={'trade_date','open','high','low','close'}
            if df.empty or not need_cols.issubset(set(df.columns)) or len(df) < 260:
                done += 1; continue
            db = pd.read_csv(pb, dtype={'trade_date':str})
            db = db[['trade_date','total_mv']].copy() if 'total_mv' in db.columns else pd.DataFrame(columns=['trade_date','total_mv'])
            db['total_mv_billion'] = pd.to_numeric(db['total_mv'], errors='coerce') / 10000.0
            df = df.sort_values('trade_date').reset_index(drop=True).merge(db[['trade_date','total_mv_billion']], on='trade_date', how='left')
            df = add_tactic_base_indicators(df)
            df = add_kdj(df)
            df = add_bbi(df)
            df = df[(df['trade_date']>=START_DATE) & (df['trade_date']<=END_DATE)].reset_index(drop=True)
            high = pd.to_numeric(df['high'], errors='coerce')
            white = pd.to_numeric(df['white_line'], errors='coerce')
            yellow = pd.to_numeric(df['yellow_line'], errors='coerce')
            jval = pd.to_numeric(df['kdj_j'], errors='coerce')
            mv = pd.to_numeric(df['total_mv_billion'], errors='coerce')
            cond=[]
            for i, td in enumerate(df['trade_date'].astype(str)):
                base_ok = (
                    (pd.notna(jval.iloc[i]) and jval.iloc[i] < get_j_threshold(td)) and
                    (pd.notna(mv.iloc[i]) and mv.iloc[i] > 100) and
                    (pd.notna(white.iloc[i]) and pd.notna(yellow.iloc[i]) and white.iloc[i] > yellow.iloc[i]) and
                    (pd.notna(high.iloc[i]) and pd.notna(white.iloc[i]) and high.iloc[i] >= white.iloc[i])
                )
                cond.append(base_ok and constrained_ok(df, i))
            sig=pd.Series(cond, index=df.index)
            for idx in df.index[sig].tolist():
                signal_date=str(df.iloc[idx]['trade_date'])
                env=omav_map.get(signal_date)
                if not env: continue
                action_weight=1.0
                if bool(env['omav_rotation_warning_flag']): action_weight*=0.5
                if bool(env['omav_bear_regime_flag']): action_weight*=0.5
                trade=simulate_trade(df, idx)
                if not trade: continue
                trade.update({'signal_date':signal_date,'code':row.ts_code,'name':row.name,'industry':row.industry,'omav':float(env['omav']) if env['omav']!='' else None,'action_weight':action_weight,'year':signal_date[:4],'month':signal_date[:6]})
                events.append(trade)
        except Exception:
            pass
        done += 1
        if done % 100 == 0 or done == total:
            save_progress('running', total, done)
    events_df=pd.DataFrame(events)
    events_df.to_csv(EVENTS_PATH, index=False, encoding='utf-8-sig')
    annual=summarize(events_df, 'year'); monthly=summarize(events_df, 'month')
    annual.to_csv(ANNUAL_PATH, index=False, encoding='utf-8-sig')
    monthly.to_csv(MONTHLY_PATH, index=False, encoding='utf-8-sig')
    result={'strategy':'b1_rebuild_v1_constrained','date_range':[START_DATE,END_DATE],'summary':summarize(events_df),'annual_path':str(ANNUAL_PATH),'monthly_path':str(MONTHLY_PATH),'events_path':str(EVENTS_PATH),'note':'第一版收束条件：回调<=15%、回调<=15天、缩量、回调阶段不超过1根放量大阴线、上涨阶段无跳空上涨；OMAV仍作为权重层'}
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save_progress('completed', total, total)
    print(RESULT_PATH)
    print(ANNUAL_PATH)
    print(MONTHLY_PATH)

if __name__ == '__main__':
    main()
