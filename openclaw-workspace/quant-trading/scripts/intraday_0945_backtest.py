#!/usr/bin/env python3
"""
09:45 盘中选股公式回测 — 方案A(分钟线) + 方案B(日线近似)

通达信公式:
  涨幅条件:=(C/REF(C,1)-1)*100>2.5 AND (C/REF(C,1)-1)*100<5;
  量比条件:=DYNAINFO(17)>1.5;  # 量比
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

import tushare as ts
from quant.config import load_settings

# ── config ──────────────────────────────────────────────────────
TRADE_CODES = ['sh601222', 'sh603803', 'sz002821', 'sz002805']
MINUTE_DIR = Path('data/minute')
OUTPUT_DIR = Path('outputs/intraday_0945')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 方案B: 日线回测区间
dt_end = datetime(2026, 4, 24)
dt_start = dt_end - timedelta(days=45)   # 取45天用于MA5计算

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

def calc_ma5(daily_df: pd.DataFrame, trade_date: str) -> dict:
    """返回 {ts_code: MA5值}  用截至 trade_date 前一日收盘的5日均线"""
    td = pd.Timestamp(trade_date)
    # 只取 trade_date 之前的交易日
    prev = daily_df[daily_df['trade_date'] < trade_date.strftime('%Y%m%d')]
    # 按 ts_code 分组取最近5天
    ma5 = {}
    for code, g in prev.groupby('ts_code'):
        g = g.sort_values('trade_date').tail(5)
        if len(g) >= 5:
            ma5[code] = g['close'].mean()
    return ma5

def code_to_ts(code: str) -> str:
    """sh601222 -> 601222.SH, sz002821 -> 002821.SZ"""
    if code.startswith('sh'):
        return code[2:] + '.SH'
    elif code.startswith('sz'):
        return code[2:] + '.SZ'
    return code

def ts_to_code(ts_code: str) -> str:
    """601222.SH -> sh601222"""
    c, ex = ts_code.split('.')
    return ex.lower() + c

# ════════════════════════════════════════════════════════════════
#  方案 A : 分钟线验证 (8个交易日 × 4只持仓股)
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

    # 3. 获取净利润 (取最近一期财报)
    fina_all = []
    for ts_code in ts_codes:
        df = pro.income(ts_code=ts_code, start_date='20250101', end_date='20260424',
                        fields='ts_code,end_date,n_income_attr_p')
        fina_all.append(df)
    fina_df = pd.concat(fina_all, ignore_index=True)
    # 每只票取最新一期
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

        # 提取每天的9:45数据
        df_min['date'] = df_min['day'].dt.date
        df_min['time'] = df_min['day'].dt.time.astype(str)

        for date in sorted(df_min['date'].unique()):
            # 跳过4/14（只有下午数据）
            if str(date) == '2026-04-14':
                continue

            day_min = df_min[df_min['date'] == date]
            t0945 = day_min[day_min['time'] == '09:45:00']
            if t0945.empty:
                continue

            price_0945 = float(t0945.iloc[0]['close'])
            # 累计成交量: 从9:30到9:45
            morn = day_min[day_min['day'].dt.time <= pd.Timestamp('09:45:00').time()]
            vol_cum = morn['volume'].sum()

            # 昨收
            prev_close = None
            prev_row = daily_df[(daily_df['ts_code'] == ts_code) &
                                (daily_df['trade_date'] == date.strftime('%Y%m%d'))]
            if not prev_row.empty:
                prev_close = float(prev_row.iloc[0]['pre_close'])

            # 当天收盘 (用于验证是否涨停)
            close_today = None
            if not prev_row.empty:
                close_today = float(prev_row.iloc[0]['close'])

            # 流通股本
            cap = None
            basic_row = basic_df[(basic_df['ts_code'] == ts_code) &
                                 (basic_df['trade_date'] == date.strftime('%Y%m%d'))]
            if not basic_row.empty:
                cap = float(basic_row.iloc[0]['float_share']) * 10000  # 转为股

            # MA5 (昨收 > MA5)
            ma5 = calc_ma5(daily_df[daily_df['ts_code'] == ts_code], date)
            ma5_val = ma5.get(ts_code)

            # 净利润
            profit = latest_profit.get(ts_code)

            # 涨幅
            if prev_close:
                pct = (price_0945 / prev_close - 1) * 100
            else:
                pct = None

            # 换手率 (9:45累计成交量 / 流通股本 * 100)
            if cap and cap > 0:
                turnover = vol_cum / cap * 100
            else:
                turnover = None

            # 流通市值 (亿元)
            if cap and cap > 0:
                float_mv = price_0945 * cap / 100000000
            else:
                float_mv = None

            # 量比: 需要过去5天同时间段的平均成交量
            # 简化为: 过去5天总成交量 / 5天 / 240分钟 × 15分钟 = 过去5天平均每分钟 × 15
            past5 = daily_df[
                (daily_df['ts_code'] == ts_code) &
                (daily_df['trade_date'] < date.strftime('%Y%m%d'))
            ].sort_values('trade_date').tail(5)
            if len(past5) >= 5:
                avg_min_vol = past5['vol'].sum() / (5 * 240)
                qrr = (vol_cum / 15) / avg_min_vol if avg_min_vol > 0 else None
            else:
                qrr = None

            # 净利润条件
            profit_ok = profit is not None and profit > 0

            # 均线条件: 昨收 > MA5
            ma_ok = prev_close is not None and ma5_val is not None and prev_close > ma5_val

            # 涨停验证
            limit_up = False
            if close_today and prev_close:
                limit_up = close_today / prev_close >= 1.098  # 近似涨停

            record = {
                'date': str(date),
                'code': code,
                'name': '',  # 后面补
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
                # 各条件判定
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
        # 补充名称
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
        if df_a['all_pass'].sum() > 0:
            print("\n通过的股票:")
            print(df_a[df_a['all_pass']][['date', 'code', 'name', 'pct_chg_0945', 'qrr', 'turnover_0945', 'float_mv_yi', 'limit_up']].to_string(index=False))
    else:
        print("无分钟线数据")

    return df_a


# ════════════════════════════════════════════════════════════════
#  方案 B : 日线近似回测 (全市场, 最近30交易日)
# ════════════════════════════════════════════════════════════════

def plan_b(pro):
    print("\n" + "=" * 60)
    print("方案 B: 日线近似回测 (全市场, 用全天数据近似9:45)")
    print("=" * 60)

    start_dt = '20260320'
    end_dt = '20260424'

    # 1. 全市场日线
    print("获取全市场日线数据...")
    daily = pro.daily(start_date=start_dt, end_date=end_dt)
    daily['trade_date'] = daily['trade_date'].astype(str)

    # 2. daily_basic (流通股本、换手率、量比)
    print("获取 daily_basic...")
    basic = pro.daily_basic(start_date=start_dt, end_date=end_dt)
    basic['trade_date'] = basic['trade_date'].astype(str)

    # 3. 净利润 (先获取股票列表, 后续按需查询)
    print("获取股票列表...")
    stock_list = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
    all_ts_codes = stock_list['ts_code'].tolist()
    print(f"全市场股票数: {len(all_ts_codes)}")

    # 4. 计算MA5
    print("计算MA5...")
    daily_sorted = daily.sort_values(['ts_code', 'trade_date'])
    daily_sorted['ma5'] = daily_sorted.groupby('ts_code')['close'].transform(lambda x: x.shift(1).rolling(5).mean())

    # 5. 合并 daily + basic
    merged = daily_sorted.merge(basic, on=['ts_code', 'trade_date'], how='left')

    # 6. 逐日筛选 (先不加净利润条件)
    dates = sorted(merged['trade_date'].unique())
    pre_signals = []

    for td in dates:
        day = merged[merged['trade_date'] == td].copy()

        # 涨幅条件
        day['pct_chg'] = pd.to_numeric(day['pct_chg'], errors='coerce')
        cond_pct = (day['pct_chg'] > 2.5) & (day['pct_chg'] < 5)

        # 量比条件 (用全天vr近似)
        day['volume_ratio'] = pd.to_numeric(day['volume_ratio'], errors='coerce')
        cond_qrr = day['volume_ratio'] > 1.5

        # 换手率条件
        day['turnover_rate_f'] = pd.to_numeric(day['turnover_rate_f'], errors='coerce')
        cond_turnover = day['turnover_rate_f'] > 3

        # 流通市值条件 (万元 -> 50亿=500000万, 300亿=3000000万)
        day['circ_mv'] = pd.to_numeric(day['circ_mv'], errors='coerce')
        cond_mv = (day['circ_mv'] > 500000) & (day['circ_mv'] <= 3000000)

        # 均线条件: 昨收 > MA5
        day['pre_close'] = pd.to_numeric(day['pre_close'], errors='coerce')
        day['ma5'] = pd.to_numeric(day['ma5'], errors='coerce')
        cond_ma = day['pre_close'] > day['ma5']

        # 先不加净利润, 筛选其他5个条件
        signal = day[cond_pct & cond_qrr & cond_turnover & cond_mv & cond_ma].copy()
        if not signal.empty:
            signal['trade_date'] = td
            pre_signals.append(signal[['ts_code', 'trade_date', 'name', 'pct_chg', 'volume_ratio',
                                       'turnover_rate_f', 'circ_mv', 'close', 'pre_close', 'ma5']])

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
                              start_date='20250101', end_date=end_dt,
                              fields='ts_code,end_date,n_income_attr_p')
            # 每只股票取最新一期
            for code, g in fina.groupby('ts_code'):
                latest = g.sort_values('end_date', ascending=False).iloc[0]
                profit_map[code] = latest['n_income_attr_p']
        except Exception as e:
            print(f"  批次 {i//batch_size+1} 出错: {e}")

    print(f"获取到净利润数据: {len(profit_map)} / {len(unique_candidates)}")

    # 8. 加入净利润条件过滤
    df_pre['profit'] = df_pre['ts_code'].map(profit_map)
    df_b = df_pre[df_pre['profit'] > 0].copy()

    # 补充名称
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
    # 对没有name的用stock_list补
    stock_name_map = dict(zip(stock_list['ts_code'], stock_list['name']))
    df_b['name'] = df_b['name'].fillna(df_b['ts_code'].map(stock_name_map))

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
    print(f"信号最多的一天: {by_date.idxmax()} ({by_date.max()}只)")
    print("\n最近5天信号:")
    recent = df_b[df_b['trade_date'] >= '20260420']
    print(recent[['trade_date', 'ts_code', 'name', 'pct_chg', 'volume_ratio', 'turnover_rate_f', 'circ_mv']].head(20).to_string(index=False))

    return df_b


# ════════════════════════════════════════════════════════════════
#  main
# ════════════════════════════════════════════════════════════════

def main():
    pro = get_tushare_pro()

    df_a = plan_a(pro)
    df_b = plan_b(pro)

    # 汇总报告
    report = {
        'generated_at': datetime.now().isoformat(),
        'plan_a': {
            'description': '分钟线验证 (4只持仓股 × 最近交易日)',
            'records': len(df_a) if not df_a.empty else 0,
            'passed': int(df_a['all_pass'].sum()) if not df_a.empty else 0,
            'limit_up_after_pass': 0,
        },
        'plan_b': {
            'description': '日线近似回测 (全市场, 全天数据近似9:45)',
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
