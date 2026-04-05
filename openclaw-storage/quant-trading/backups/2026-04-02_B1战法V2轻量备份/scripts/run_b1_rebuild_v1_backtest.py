#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quant.indicators import add_tactic_base_indicators

START_DATE='20230101'
END_DATE='20260401'
PROGRESS_PATH = ROOT / 'outputs' / 'b1_rebuild_v1_backtest_progress.json'
RESULT_PATH = ROOT / 'outputs' / 'b1_rebuild_v1_backtest.json'
EVENTS_PATH = ROOT / 'outputs' / 'b1_rebuild_v1_backtest_events.csv'
ANNUAL_PATH = ROOT / 'outputs' / 'b1_rebuild_v1_backtest_annual.csv'
MONTHLY_PATH = ROOT / 'outputs' / 'b1_rebuild_v1_backtest_monthly.csv'


def save_progress(status,total,done):
    pct=round(done/total*100,2) if total else 100.0
    PROGRESS_PATH.write_text(json.dumps({'task':'b1_rebuild_v1_backtest','status':status,'updated_at':time.strftime('%Y-%m-%d %H:%M:%S'),'total_codes':total,'completed_codes':done,'progress_pct':pct,'start_date':START_DATE,'end_date':END_DATE}, ensure_ascii=False, indent=2), encoding='utf-8')


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


def get_j_threshold(trade_date):
    y=str(trade_date)[:4]
    if y == '2023': return -10
    if y == '2024': return 0
    if y == '2025': return 18
    return 25


def add_bbi(df):
    out=df.copy()
    close=pd.to_numeric(out['close'], errors='coerce')
    out['bbi'] = (close.rolling(3).mean() + close.rolling(6).mean() + close.rolling(12).mean() + close.rolling(24).mean()) / 4
    return out


def simulate_trade(df, idx, quality_good=False):
    if idx + 1 >= len(df):
        return None
    entry_i = idx + 1
    entry_price = float(df.iloc[entry_i]['open'])
    if pd.isna(entry_price) or entry_price <= 0:
        return None
    exit_i = None
    exit_reason = 'end_of_data'
    red_body_prev = None
    break_line_days = 0
    for j in range(entry_i, len(df)):
        row = df.iloc[j]
        open_px = float(row['open'])
        close_px = float(row['close'])
        body = abs(close_px - open_px)
        is_green = close_px < open_px
        is_red = close_px > open_px
        # 止盈：3/4阴量线（按实体长度）
        if j > entry_i:
            prev = df.iloc[j-1]
            prev_open = float(prev['open']); prev_close = float(prev['close'])
            prev_red_body = abs(prev_close - prev_open) if prev_close > prev_open else None
            if is_green and prev_red_body and prev_red_body > 0:
                ratio = body / prev_red_body
                if 0.65 <= ratio <= 0.85:
                    exit_i = j; exit_reason = 'three_quarter_green_body_takeprofit'; break
        # 止损：跌破 BBI 2日；优质票可改黄线2日
        ref_line = pd.to_numeric(row['yellow_line'], errors='coerce') if quality_good else pd.to_numeric(row['bbi'], errors='coerce')
        if pd.notna(ref_line) and close_px < ref_line:
            break_line_days += 1
        else:
            break_line_days = 0
        if break_line_days >= 2:
            exit_i = j; exit_reason = 'break_bbi_or_yellow_2days'; break
    if exit_i is None:
        exit_i = len(df)-1
    exit_price = float(df.iloc[exit_i]['close'])
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
    out=g.agg(event_count=('code','count'),signal_days=('signal_date','nunique'),win_rate=('return_pct', lambda s: round((pd.to_numeric(s, errors='coerce')>0).mean()*100,2)),avg_return_pct=('return_pct', lambda s: round(pd.to_numeric(s, errors='coerce').mean(),4)),median_return_pct=('return_pct', lambda s: round(pd.to_numeric(s, errors='coerce').median(),4))).reset_index()
    return out


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
            done += 1
            continue
        try:
            df = pd.read_csv(p, usecols=['trade_date','open','high','low','close'], dtype={'trade_date':str})
            db = pd.read_csv(pb, dtype={'trade_date':str})
            if df.empty or len(df) < 260:
                done += 1
                continue
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
            cond = []
            for i, td in enumerate(df['trade_date'].astype(str)):
                cond.append(
                    (pd.notna(jval.iloc[i]) and jval.iloc[i] < get_j_threshold(td)) and
                    (pd.notna(mv.iloc[i]) and mv.iloc[i] > 100) and
                    (pd.notna(white.iloc[i]) and pd.notna(yellow.iloc[i]) and white.iloc[i] > yellow.iloc[i]) and
                    (pd.notna(high.iloc[i]) and pd.notna(white.iloc[i]) and high.iloc[i] >= white.iloc[i])
                )
            sig = pd.Series(cond, index=df.index)
            for idx in df.index[sig].tolist():
                signal_date = str(df.iloc[idx]['trade_date'])
                env = omav_map.get(signal_date)
                if not env:
                    continue
                action_weight = 1.0
                if bool(env['omav_rotation_warning_flag']):
                    action_weight *= 0.5
                if bool(env['omav_bear_regime_flag']):
                    action_weight *= 0.5
                trade = simulate_trade(df, idx, quality_good=False)
                if not trade:
                    continue
                trade.update({'signal_date':signal_date,'code':row.ts_code,'name':row.name,'industry':row.industry,'omav':float(env['omav']) if env['omav']!='' else None,'action_weight':action_weight,'year':signal_date[:4],'month':signal_date[:6]})
                events.append(trade)
        except Exception:
            pass
        done += 1
        if done % 100 == 0 or done == total:
            save_progress('running', total, done)
    events_df = pd.DataFrame(events)
    events_df.to_csv(EVENTS_PATH, index=False, encoding='utf-8-sig')
    annual = summarize(events_df, 'year')
    monthly = summarize(events_df, 'month')
    annual.to_csv(ANNUAL_PATH, index=False, encoding='utf-8-sig')
    monthly.to_csv(MONTHLY_PATH, index=False, encoding='utf-8-sig')
    result = {'strategy':'b1_rebuild_v1','date_range':[START_DATE,END_DATE],'summary':summarize(events_df),'annual_path':str(ANNUAL_PATH),'monthly_path':str(MONTHLY_PATH),'events_path':str(EVENTS_PATH),'note':'OMAV作为权重/频率层已写入事件明细 action_weight，当前主结果先看原始命中样本统计'}
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save_progress('completed', total, total)
    print(RESULT_PATH)
    print(ANNUAL_PATH)
    print(MONTHLY_PATH)

if __name__ == '__main__':
    main()
