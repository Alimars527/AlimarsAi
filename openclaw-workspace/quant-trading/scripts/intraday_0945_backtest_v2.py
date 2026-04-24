#!/usr/bin/env python3
"""
09:45 盘中选股公式回测 — 方案A(分钟线) + 方案B(日线近似, 本地数据)

通达信公式:
  涨幅条件:=(C/REF(C,1)-1)*100>2.5 AND (C/REF(C,1)-1)*100<5;
  量比条件:=DYNAINFO(17)>1.5;
  换手率条件:=VOL/CAPITAL*100>3;
  流通市值条件:=C*CAPITAL*100/100000000>50 AND C*CAPITAL*100/100000000<=300;
  净利润条件:=FINANCE(30)>0;
  均线条件:=REF(C,1)>MA(C,5);
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import glob

import tushare as ts
from quant.config import load_settings

# ── config ──────────────────────────────────────────────────────
TRADE_CODES = ['sh601222', 'sh603803', 'sz002821', 'sz002805']
MINUTE_DIR = Path('data/minute')
DAILY_DIR = Path('data/daily')
DAILY_BASIC_DIR = Path('data/daily_basic')
OUTPUT_DIR = Path('outputs/intraday_0945')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 方案B: 日线回测区间 (避开daily_basic中volume_ratio为NaN的最近2天)
B_END_DATE = '20260422'
B_START_DATE = '20260301'

# ── helpers ─────────────────────────────────────────────────────

def get_tushare_pro():
    settings = load_settings()
    token = settings.get('tushare_token')
    return ts.pro_api(token)

def load_minute(code: str) -> pd.DataFrame:
    path = MINUTE_DIR / f'{code}_minute.csv'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df['day'] = pd.to_datetime(df['day'])
    return df

def load_local_daily(ts_code: str) -> pd.DataFrame:
    path = DAILY_DIR / f'{ts_code}.csv'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df['trade_date'] = df['trade_date'].astype(str)
    return df

def load_local_daily_basic(ts_code: str) -> pd.DataFrame:
    path = DAILY_BASIC_DIR / f'{ts_code}.csv'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df['trade_date'] = df['trade_date'].astype(str)
    return df

def code_to_ts(code: str) -> str:
    if code.startswith('sh'):
        return code[2:] + '.SH'
    elif code.startswith('sz'):
        return code[2:] + '.SZ'
    return code

def ts_to_code(ts_code: str) -> str:
    c, ex = ts_code.split('.')
    return ex.lower() + c

# ════════════════════════════════════════════════════════════════
#  方案 A : 分钟线验证 (4只持仓股 × 最近交易日)
# ════════════════════════════════════════════════════════════════

def plan_a(pro):
    print("=" * 60)
    print("方案 A: 分钟线验证 (4只持仓股 × 最近交易日)")
    print("=" * 60)

    # 1. 获取这4只票的日线数据 (用于昨收、MA5)
    ts_codes = [code_to_ts(c) for c in TRADE_CODES]
    daily_all = []
    for ts_code in ts_codes:
        df = pro.daily(ts_code=ts_code, start_date='20260401', end_date='20260424')
        daily_all.append(df)
    daily_df = pd.concat(daily_all, ignore_index=True)
    daily_df['trade_date'] = daily_df['trade_date'].astype(str)

    # 2. 获取 daily_basic (流通股本 capital, 换手率)
    basic_all = []
    for ts_code in ts_codes:
        df = pro.daily_basic(ts_code=ts_code, start_date='20260401', end_date='20260424')
        basic_all.append(df)
    basic_df = pd.concat(basic_all, ignore_index=True)
    basic_df['trade_date'] = basic_df['trade_date'].astype(str)

    # 3. 获取净利润 (取最近一期)
    fina_all = []
    for ts_code in ts_codes:
        df = pro.income(ts_code=ts_code, start_date='20250101', end_date='20260424',
                        fields='ts_code,end_date,n_income_attr_p')
        fina_all.append(df)
    fina_df = pd.concat(fina_all, ignore_index=True)
    latest_profit = {}
    for code, g in fina_df.groupby('ts_code'):
        g = g.sort_values('end_date', ascending=False)
        latest_profit[code] = g.iloc[0]['n_income_attr_p']

    results = []

    for code in TRADE_CODES:
        ts_code = code_to_ts(code)
        df_min = load_minute(code)
        if df_min.empty:
            continue

        df_min['date'] = df_min['day'].dt.date
        df_min['time'] = df_min['day'].dt.time.astype(str)

        for date in sorted(df_min['date'].unique()):
            if str(date) == '2026-04-14':
                continue

            day_min = df_min[df_min['date'] == date]
            t0945 = day_min[day_min['time'] == '09:45:00']
            if t0945.empty:
                continue

            price_0945 = float(t0945.iloc[0]['close'])
            morn = day_min[day_min['day'].dt.time <= pd.Timestamp('09:45:00').time()]
            vol_cum = morn['volume'].sum()

            prev_close = None
            prev_row = daily_df[(daily_df['ts_code'] == ts_code) &
                                (daily_df['trade_date'] == date.strftime('%Y%m%d'))]
            if not prev_row.empty:
                prev_close = float(prev_row.iloc[0]['pre_close'])

            close_today = None
            if not prev_row.empty:
                close_today = float(prev_row.iloc[0]['close'])

            cap = None
            basic_row = basic_df[(basic_df['ts_code'] == ts_code) &
                                 (basic_df['trade_date'] == date.strftime('%Y%m%d'))]
            if not basic_row.empty:
                cap = float(basic_row.iloc[0]['float_share']) * 10000

            # MA5 (用本地daily数据计算更可靠)
            local_daily = load_local_daily(ts_code)
            local_daily['trade_date'] = local_daily['trade_date'].astype(str)
            past5 = local_daily[local_daily['trade_date'] < date.strftime('%Y%m%d')].tail(5)
            ma5_val = past5['close'].mean() if len(past5) >= 5 else None

            profit = latest_profit.get(ts_code)

            if prev_close:
                pct = (price_0945 / prev_close - 1) * 100
            else:
                pct = None

            if cap and cap > 0:
                turnover = vol_cum / cap * 100
            else:
                turnover = None

            if cap and cap > 0:
                float_mv = price_0945 * cap / 100000000
            else:
                float_mv = None

            # 量比: 分钟线volume是股, 日线vol是手 -> 统一为手
            if len(past5) >= 5:
                # 获取对应日期的日线vol (手)
                past5_td = past5['trade_date'].tolist()
                daily_past5 = daily_df[
                    (daily_df['ts_code'] == ts_code) &
                    (daily_df['trade_date'].isin(past5_td))
                ]
                if len(daily_past5) >= 5:
                    avg_min_vol = daily_past5['vol'].sum() / (5 * 240)
                    qrr = (vol_cum / 100 / 15) / avg_min_vol if avg_min_vol > 0 else None
                else:
                    qrr = None
            else:
                qrr = None

            profit_ok = profit is not None and profit > 0
            ma_ok = prev_close is not None and ma5_val is not None and prev_close > ma5_val

            limit_up = False
            if close_today and prev_close:
                limit_up = close_today / prev_close >= 1.098

            record = {
                'date': str(date),
                'code': code,
                'name': '',
                'price_0945': round(price_0945, 3),
                'prev_close': round(prev_close, 3) if prev_close else None,
                'pct_chg_0945': round(pct, 2) if pct is not None else None,
                'vol_cum_0945': int(vol_cum),
                'qrr': round(qrr, 2) if qrr is not None else None,
                'turnover_0945': round(turnover, 2) if turnover is not None else None,
                'float_mv_yi': round(float_mv, 2) if float_mv is not None else None,
                'profit_yi': round(profit / 100000000, 2) if profit is not None else None,
                'profit_ok': profit_ok,
                'ma5': round(ma5_val, 3) if ma5_val else None,
                'ma_ok': ma_ok,
                'close_today': round(close_today, 3) if close_today else None,
                'limit_up': limit_up,
                'cond_pct': 2.5 < pct < 5 if pct is not None else False,
                'cond_qrr': qrr > 1.5 if qrr is not None else False,
                'cond_turnover': turnover > 3 if turnover is not None else False,
                'cond_mv': 50 < float_mv <= 300 if float_mv is not None else False,
                'cond_profit': profit_ok,
                'cond_ma': ma_ok,
                'all_pass': (2.5 < pct < 5 if pct else False) and
                            (qrr > 1.5 if qrr else False) and
                            (turnover > 3 if turnover else False) and
                            (50 < float_mv <= 300 if float_mv else False) and
                            profit_ok and ma_ok,
            }
            results.append(record)

    df_a = pd.DataFrame(results)
    if not df_a.empty:
        names = {}
        for ts_code in ts_codes:
            info = pro.stock_basic(ts_code=ts_code, fields='ts_code,name')
            if not info.empty:
                names[ts_code] = info.iloc[0]['name']
        df_a['name'] = df_a['code'].apply(lambda c: names.get(code_to_ts(c), ''))
        df_a = df_a.sort_values(['date', 'code'])
        out_a = OUTPUT_DIR / 'plan_a_minute_verification.csv'
        df_a.to_csv(out_a, index=False, encoding='utf-8-sig')
        print(f"\n方案A结果已保存: {out_a}")
        print(f"共 {len(df_a)} 条记录, 全部通过: {df_a['all_pass'].sum()} 条")
        print("\n各条件通过情况:")
        for col in ['cond_pct', 'cond_qrr', 'cond_turnover', 'cond_mv', 'cond_profit', 'cond_ma']:
            passed = df_a[col].sum()
            print(f"  {col}: {passed} / {len(df_a)} ({passed/len(df_a)*100:.1f}%)")
        if df_a['all_pass'].sum() > 0:
            print("\n通过的股票:")
            print(df_a[df_a['all_pass']][['date', 'code', 'name', 'pct_chg_0945', 'qrr', 'turnover_0945', 'float_mv_yi', 'limit_up']].to_string(index=False))
    else:
        print("无分钟线数据")

    return df_a


# ════════════════════════════════════════════════════════════════
#  方案 B : 日线近似回测 (全市场, 本地数据)
# ════════════════════════════════════════════════════════════════

def plan_b(pro):
    print("\n" + "=" * 60)
    print("方案 B: 日线近似回测 (全市场, 本地数据)")
    print(f"回测区间: {B_START_DATE} ~ {B_END_DATE}")
    print("=" * 60)

    # 1. 获取所有本地 daily 和 daily_basic 文件
    daily_files = glob.glob(str(DAILY_DIR / '*.csv'))
    basic_files = glob.glob(str(DAILY_BASIC_DIR / '*.csv'))
    daily_codes = {Path(f).stem for f in daily_files}
    basic_codes = {Path(f).stem for f in basic_files}
    common_codes = sorted(daily_codes & basic_codes)
    print(f"本地 daily 文件: {len(daily_files)}, daily_basic: {len(basic_files)}, 共同: {len(common_codes)}")

    # 2. 构建全市场 DataFrame (只读回测区间)
    all_daily = []
    all_basic = []

    for ts_code in common_codes:
        df_d = load_local_daily(ts_code)
        df_b = load_local_daily_basic(ts_code)
        if df_d.empty or df_b.empty:
            continue
        # 过滤回测区间
        df_d = df_d[(df_d['trade_date'] >= B_START_DATE) & (df_d['trade_date'] <= B_END_DATE)]
        df_b = df_b[(df_b['trade_date'] >= B_START_DATE) & (df_b['trade_date'] <= B_END_DATE)]
        if df_d.empty or df_b.empty:
            continue
        all_daily.append(df_d)
        all_basic.append(df_b)

    if not all_daily:
        print("无本地数据")
        return pd.DataFrame()

    daily_all = pd.concat(all_daily, ignore_index=True)
    basic_all = pd.concat(all_basic, ignore_index=True)

    # 3. 计算MA5
    print("计算MA5...")
    daily_sorted = daily_all.sort_values(['ts_code', 'trade_date'])
    daily_sorted['ma5'] = daily_sorted.groupby('ts_code')['close'].transform(lambda x: x.shift(1).rolling(5).mean())

    # 4. 合并 daily + basic
    merged = daily_sorted.merge(basic_all, on=['ts_code', 'trade_date'], how='left')

    # 5. 计算量比 (如果 volume_ratio 缺失)
    print("计算量比...")
    merged['volume_ratio'] = pd.to_numeric(merged['volume_ratio'], errors='coerce')
    merged['vol'] = pd.to_numeric(merged['vol'], errors='coerce')

    # 对于 volume_ratio 为 NaN 的, 用 vol 计算
    def calc_missing_qrr(group):
        group = group.sort_values('trade_date')
        avg5 = group['vol'].shift(1).rolling(5).mean()
        mask = group['volume_ratio'].isna()
        group.loc[mask, 'volume_ratio'] = group.loc[mask, 'vol'] / avg5.loc[mask]
        return group

    merged = merged.groupby('ts_code', group_keys=False).apply(calc_missing_qrr)

    # 6. 逐日筛选 (先不加净利润条件)
    dates = sorted(merged['trade_date'].unique())
    pre_signals = []

    for td in dates:
        day = merged[merged['trade_date'] == td].copy()

        day['pct_chg'] = pd.to_numeric(day['pct_chg'], errors='coerce')
        cond_pct = (day['pct_chg'] > 2.5) & (day['pct_chg'] < 5)

        day['volume_ratio'] = pd.to_numeric(day['volume_ratio'], errors='coerce')
        cond_qrr = day['volume_ratio'] > 1.5

        day['turnover_rate_f'] = pd.to_numeric(day['turnover_rate_f'], errors='coerce')
        cond_turnover = day['turnover_rate_f'] > 3

        # circ_mv 单位是万元, 50亿=500000万, 300亿=3000000万
        day['circ_mv'] = pd.to_numeric(day['circ_mv'], errors='coerce')
        cond_mv = (day['circ_mv'] > 500000) & (day['circ_mv'] <= 3000000)

        day['pre_close'] = pd.to_numeric(day['pre_close'], errors='coerce')
        day['ma5'] = pd.to_numeric(day['ma5'], errors='coerce')
        cond_ma = day['pre_close'] > day['ma5']

        signal = day[cond_pct & cond_qrr & cond_turnover & cond_mv & cond_ma].copy()
        if not signal.empty:
            signal['trade_date'] = td
            pre_signals.append(signal[['ts_code', 'trade_date', 'name', 'pct_chg', 'volume_ratio',
                                       'turnover_rate_f', 'circ_mv', 'close', 'pre_close', 'ma5', 'vol']])

    if not pre_signals:
        print("日线近似回测无信号(前5个条件)")
        return pd.DataFrame()

    df_pre = pd.concat(pre_signals, ignore_index=True)

    # 7. 对候选股票获取净利润 (分批)
    unique_candidates = df_pre['ts_code'].unique().tolist()
    print(f"前5个条件候选股票数: {len(unique_candidates)}, 分批获取净利润...")

    profit_map = {}
    batch_size = 80
    for i in range(0, len(unique_candidates), batch_size):
        batch = unique_candidates[i:i+batch_size]
        try:
            fina = pro.income(ts_code=','.join(batch),
                              start_date='20250101', end_date='20260424',
                              fields='ts_code,end_date,n_income_attr_p')
            for code, g in fina.groupby('ts_code'):
                latest = g.sort_values('end_date', ascending=False).iloc[0]
                profit_map[code] = latest['n_income_attr_p']
        except Exception as e:
            print(f"  批次 {i//batch_size+1} 出错: {e}")

    print(f"获取到净利润数据: {len(profit_map)} / {len(unique_candidates)}")

    # 8. 加入净利润条件过滤
    df_pre['profit'] = df_pre['ts_code'].map(profit_map)
    df_b = df_pre[df_pre['profit'] > 0].copy()

    # 补充名称 (用 stock_basic 接口)
    names_map = {}
    unique_codes = df_b['ts_code'].unique().tolist()
    print(f"补充 {len(unique_codes)} 只股票名称...")
    for i in range(0, len(unique_codes), 100):
        batch = unique_codes[i:i+100]
        try:
            info = pro.stock_basic(ts_code=','.join(batch), fields='ts_code,name')
            for _, r in info.iterrows():
                names_map[r['ts_code']] = r['name']
        except Exception as e:
            print(f"获取名称出错: {e}")
    df_b['name'] = df_b['ts_code'].map(names_map)

    # 统计
    total_signals = len(df_b)
    by_date = df_b.groupby('trade_date').size()
    avg_per_day = by_date.mean()

    out_b = OUTPUT_DIR / 'plan_b_daily_approx.csv'
    df_b.to_csv(out_b, index=False, encoding='utf-8-sig')

    print(f"\n方案B结果已保存: {out_b}")
    print(f"总信号数(6条件全满足): {total_signals}")
    print(f"有信号交易日: {len(by_date)} / {len(dates)}")
    print(f"平均每天信号数: {avg_per_day:.1f}")
    if len(by_date) > 0:
        print(f"信号最多的一天: {by_date.idxmax()} ({by_date.max()}只)")
        print("\n最近5天信号:")
        recent = df_b[df_b['trade_date'] >= '20260415']
        print(recent[['trade_date', 'ts_code', 'name', 'pct_chg', 'volume_ratio', 'turnover_rate_f', 'circ_mv']].head(30).to_string(index=False))
    else:
        print("无信号")

    return df_b


# ════════════════════════════════════════════════════════════════
#  main
# ════════════════════════════════════════════════════════════════

def main():
    pro = get_tushare_pro()

    df_a = plan_a(pro)
    df_b = plan_b(pro)

    report = {
        'generated_at': datetime.now().isoformat(),
        'plan_a': {
            'description': '分钟线验证 (4只持仓股 × 最近交易日)',
            'records': len(df_a) if not df_a.empty else 0,
            'passed': int(df_a['all_pass'].sum()) if not df_a.empty else 0,
            'limit_up_after_pass': 0,
        },
        'plan_b': {
            'description': '日线近似回测 (全市场, 本地数据)',
            'records': len(df_b) if not df_b.empty else 0,
            'trading_days_with_signals': 0,
            'avg_per_day': 0,
        },
    }

    if not df_a.empty and df_a['all_pass'].sum() > 0:
        passed = df_a[df_a['all_pass']]
        report['plan_a']['limit_up_after_pass'] = int(passed['limit_up'].sum())

    if not df_b.empty:
        by_date = df_b.groupby('trade_date').size()
        report['plan_b']['trading_days_with_signals'] = len(by_date)
        report['plan_b']['avg_per_day'] = round(by_date.mean(), 2)

    out_json = OUTPUT_DIR / 'report.json'
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n汇总报告: {out_json}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
