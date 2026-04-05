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
PROGRESS_PATH = ROOT / 'outputs' / 'brick_strategy_v2_with_rotation_top5_backtest_progress.json'
RESULT_PATH = ROOT / 'outputs' / 'brick_strategy_v2_with_rotation_top5_backtest.json'
EVENTS_PATH = ROOT / 'outputs' / 'brick_strategy_v2_with_rotation_top5_backtest_events.csv'


def save_progress(status,total,done):
    pct=round(done/total*100,2) if total else 100.0
    PROGRESS_PATH.write_text(json.dumps({'task':'brick_strategy_v2_with_rotation_top5_backtest','status':status,'updated_at':time.strftime('%Y-%m-%d %H:%M:%S'),'total_codes':total,'completed_codes':done,'progress_pct':pct}, ensure_ascii=False, indent=2), encoding='utf-8')


def build_signal(df):
    z = pd.to_numeric(df['brick_formula_value'], errors='coerce').fillna(0)
    green = df['brick_formula_green'].fillna(False).astype(bool)
    xg = df['brick_raw_turn_red'].fillna(False).astype(bool)
    white = pd.to_numeric(df['white_line'], errors='coerce')
    yellow = pd.to_numeric(df['yellow_line'], errors='coerce')
    high = pd.to_numeric(df['high'], errors='coerce')
    return (
        xg & (high >= white) & (white > yellow)
        & green.shift(1, fill_value=False) & green.shift(2, fill_value=False)
        & green.shift(3, fill_value=False) & green.shift(4, fill_value=False)
        & (z.shift(4) > z.shift(3)) & (z.shift(3) > z.shift(2))
        & (z.shift(2) > z.shift(1)) & (z >= z.shift(1))
        & df['brick_history_ok'].fillna(False).astype(bool)
    )


def simulate_trade(df, idx):
    if idx+1 >= len(df): return None
    entry_i = idx+1
    entry_price = float(df.iloc[entry_i]['open'])
    if pd.isna(entry_price) or entry_price <= 0: return None
    red_seen=0; exit_i=None; exit_reason='end_of_data'
    for j in range(entry_i, len(df)):
        row=df.iloc[j]
        open_px=float(row['open'])
        brick_val=float(row['brick_formula_value'])
        prev_brick_val=float(df.iloc[j-1]['brick_formula_value']) if j>0 else brick_val
        green_brick=bool(row['brick_formula_green'])
        red_brick=brick_val > prev_brick_val
        if j == entry_i + 1:
            gap_pct=(open_px/entry_price - 1)*100 if entry_price else 0
            if gap_pct < 2.0:
                exit_i=j; exit_reason='next_day_open_no_surge'; break
        if red_brick: red_seen += 1
        if green_brick:
            exit_i=j; exit_reason='green_brick_exit'; break
        if red_seen >= 4:
            exit_i=j; exit_reason='max_4_red_bricks'; break
    if exit_i is None: exit_i=len(df)-1
    exit_price=float(df.iloc[exit_i]['close'])
    return {'entry_date':str(df.iloc[entry_i]['trade_date']),'exit_date':str(df.iloc[exit_i]['trade_date']),'entry_price':entry_price,'exit_price':exit_price,'return_pct':(exit_price/entry_price-1)*100,'holding_days':int(exit_i-entry_i+1),'exit_reason':exit_reason}


def summarize(df):
    if df.empty:
        return {'event_count':0,'signal_days':0,'win_rate':0,'avg_return_pct':0,'median_return_pct':0}
    ret = pd.to_numeric(df['return_pct'], errors='coerce')
    return {'event_count':int(len(df)),'signal_days':int(df['signal_date'].nunique()),'win_rate':round((ret>0).mean()*100,2),'avg_return_pct':round(ret.mean(),4),'median_return_pct':round(ret.median(),4)}


def main():
    omav = pd.read_csv(ROOT / 'data' / 'omav' / 'omav_daily_standardized_20260402.csv', dtype={'trade_date':str})
    omav = omav[(omav['trade_date']>=START_DATE) & (omav['trade_date']<=END_DATE)].copy()
    omav['omav_rotation_warning_flag'] = omav['omav_rotation_warning_flag'].astype(str).str.lower().eq('true')
    omav['omav_bear_regime_flag'] = omav['omav_bear_regime_flag'].astype(str).str.lower().eq('true')
    omav_map = omav.set_index('trade_date')[['omav','omav_rotation_warning_flag','omav_bear_regime_flag']].to_dict('index')

    meta = pd.read_csv(ROOT / 'data' / 'meta' / 'stock_basic.csv', dtype=str).fillna('')
    meta = meta[~meta['ts_code'].astype(str).str.endswith('.BJ')]
    meta = meta[~meta['name'].astype(str).str.contains('ST', case=False, na=False)]
    meta = meta[~meta['ts_code'].astype(str).str.startswith(('300','301'))]
    meta = meta[~meta['industry'].astype(str).str.contains('房地产', na=False)]

    # industry ranking table
    daily_rows=[]
    total=len(meta); done=0; save_progress('running', total, 0)
    for row in meta[['ts_code','industry']].itertuples(index=False):
        p=ROOT/'data'/'daily'/f'{row.ts_code}.csv'
        done += 1
        if done % 200 == 0 or done == total: save_progress('running', total, done)
        if not p.exists() or not row.industry: continue
        try:
            df=pd.read_csv(p, usecols=['trade_date','pct_chg'], dtype={'trade_date':str})
            if df.empty: continue
            df=df[(df['trade_date']>=START_DATE) & (df['trade_date']<=END_DATE)].copy()
            df['pct_chg']=pd.to_numeric(df['pct_chg'], errors='coerce')
            df['industry']=row.industry
            daily_rows.append(df[['trade_date','industry','pct_chg']])
        except Exception:
            continue
    ind=pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame(columns=['trade_date','industry','pct_chg'])
    board=ind.groupby(['trade_date','industry'], as_index=False)['pct_chg'].mean().sort_values(['trade_date','pct_chg'], ascending=[True,False])
    board['rank']=board.groupby('trade_date')['pct_chg'].rank(method='first', ascending=False)
    rotation_map=board[board['rank']<=5].assign(flag=True).set_index(['trade_date','industry'])['flag'].to_dict()

    # backtest
    events=[]; done=0; save_progress('running', total, 0)
    for row in meta[['ts_code','name','industry']].itertuples(index=False):
        p=ROOT/'data'/'daily'/f'{row.ts_code}.csv'
        if not p.exists():
            done += 1; continue
        try:
            df=pd.read_csv(p, usecols=['trade_date','open','high','low','close'], dtype={'trade_date':str})
            if df.empty or len(df)<260:
                done += 1; continue
            df=df.sort_values('trade_date').reset_index(drop=True)
            df=add_tactic_base_indicators(df)
            df=add_brick_formula_flags(df)
            df=df[(df['trade_date']>=START_DATE) & (df['trade_date']<=END_DATE)].reset_index(drop=True)
            sig=build_signal(df)
            for idx in df.index[sig].tolist():
                signal_date=str(df.iloc[idx]['trade_date'])
                env=omav_map.get(signal_date)
                if not env: continue
                if bool(env['omav_bear_regime_flag']) or bool(env['omav_rotation_warning_flag']): continue
                if not rotation_map.get((signal_date, row.industry), False): continue
                trade=simulate_trade(df, idx)
                if not trade: continue
                trade.update({'signal_date':signal_date,'code':row.ts_code,'name':row.name,'industry':row.industry,'omav':float(env['omav']) if env['omav']!='' else None})
                events.append(trade)
        except Exception:
            pass
        done += 1
        if done % 100 == 0 or done == total: save_progress('running', total, done)
    events_df=pd.DataFrame(events)
    events_df.to_csv(EVENTS_PATH, index=False, encoding='utf-8-sig')
    result={'strategy':'brick_strategy_v2_with_rotation_top5','date_range':[START_DATE,END_DATE],'summary':summarize(events_df),'events_path':str(EVENTS_PATH),'rotation_rule':'rank<=5 only','base_version':'V2=优质砖型图V1+OMAV硬过滤'}
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save_progress('completed', total, total)
    print(RESULT_PATH)

if __name__ == '__main__':
    main()
