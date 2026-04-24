#!/usr/bin/env python3
"""
涨停票9:45条件反推分析

思路: 拉取近半个月涨停股票的当日分钟线, 反推9:45时是否满足选股公式条件
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
import glob
import time

import akshare as ak
import tushare as ts
from quant.config import load_settings

# ── config ──────────────────────────────────────────────────────
RECENT_DATES = ['20260410','20260413','20260414','20260415','20260416',
                '20260417','20260420','20260421','20260422','20260423','20260424']
DAILY_DIR = Path('data/daily')
DAILY_BASIC_DIR = Path('data/daily_basic')
OUTPUT_DIR = Path('outputs/intraday_0945')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── helpers ─────────────────────────────────────────────────────

def get_tushare_pro():
    settings = load_settings()
    token = settings.get('tushare_token')
    return ts.pro_api(token)

def ts_to_ak_symbol(ts_code: str) -> str:
    """601222.SH -> sh601222"""
    c, ex = ts_code.split('.')
    return ex.lower() + c

def load_local_daily(ts_code: str) -> pd.DataFrame:
    path = DAILY_DIR / f'{ts_code}.csv'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df['trade_date'] = df['trade_date'].astype(str)
    return df

def load_local_basic(ts_code: str) -> pd.DataFrame:
    path = DAILY_BASIC_DIR / f'{ts_code}.csv'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df['trade_date'] = df['trade_date'].astype(str)
    return df

# ════════════════════════════════════════════════════════════════
#  1. 找出近半个月所有涨停票
# ════════════════════════════════════════════════════════════════

def find_limit_up_stocks():
    print("=" * 60)
    print("Step 1: 找出近半个月涨停票")
    print("=" * 60)

    records = []  # (ts_code, trade_date, pct_chg)
    for f in glob.glob(str(DAILY_DIR / '*.csv')):
        df = pd.read_csv(f)
        df['trade_date'] = df['trade_date'].astype(str)
        for td in RECENT_DATES:
            row = df[df['trade_date'] == td]
            if not row.empty:
                pct = float(row.iloc[0]['pct_chg'])
                if pct >= 9.5:
                    ts_code = row.iloc[0]['ts_code']
                    records.append((ts_code, td, pct))

    print(f"总涨停记录: {len(records)}")
    by_date = Counter(td for _, td, _ in records)
    for td in RECENT_DATES:
        print(f"  {td}: {by_date.get(td, 0)}只")

    return records


# ════════════════════════════════════════════════════════════════
#  2. 获取分钟线并分析9:45条件
# ════════════════════════════════════════════════════════════════

def analyze_minute_data(records):
    print("\n" + "=" * 60)
    print("Step 2: 拉取分钟线并分析9:45条件")
    print("=" * 60)

    # Group by stock to minimize akshare calls
    stock_dates = defaultdict(list)
    for ts_code, td, pct in records:
        stock_dates[ts_code].append((td, pct))

    unique_stocks = list(stock_dates.keys())
    print(f"去重后股票数: {len(unique_stocks)}")

    results = []
    failed_stocks = []

    for i, ts_code in enumerate(unique_stocks):
        if i % 50 == 0:
            print(f"  进度: {i}/{len(unique_stocks)} ({i/len(unique_stocks)*100:.1f}%)")

        ak_symbol = ts_to_ak_symbol(ts_code)

        try:
            # 拉取分钟线 (包含最近多天的数据)
            df_min = ak.stock_zh_a_minute(symbol=ak_symbol, period='1', adjust='qfq')
            time.sleep(0.3)  # 避免限流
        except Exception as e:
            failed_stocks.append((ts_code, str(e)))
            continue

        if df_min is None or df_min.empty:
            failed_stocks.append((ts_code, 'empty_data'))
            continue

        df_min['day'] = pd.to_datetime(df_min['day'])
        df_min['date'] = df_min['day'].dt.date
        df_min['time'] = df_min['day'].dt.time.astype(str)

        # 本地日线数据 (用于MA5、量比、流通股本)
        local_daily = load_local_daily(ts_code)
        local_basic = load_local_basic(ts_code)

        for td, pct in stock_dates[ts_code]:
            td_date = datetime.strptime(td, '%Y%m%d').date()

            # 检查分钟线是否包含该日期
            day_min = df_min[df_min['date'] == td_date]
            if day_min.empty:
                continue

            # 9:45数据
            t0945 = day_min[day_min['time'] == '09:45:00']
            if t0945.empty:
                continue

            price_0945 = float(t0945.iloc[0]['close'])

            # 累计成交量 (9:30~9:45)
            morn = day_min[day_min['day'].dt.time <= pd.Timestamp('09:45:00').time()]
            vol_cum = pd.to_numeric(morn['volume'], errors='coerce').sum()  # 股

            # 昨收
            prev_close = None
            if not local_daily.empty:
                prev_row = local_daily[local_daily['trade_date'] == td]
                if not prev_row.empty:
                    prev_close = float(prev_row.iloc[0]['pre_close'])

            # 流通股本 (股)
            cap = None
            if not local_basic.empty:
                basic_row = local_basic[local_basic['trade_date'] == td]
                if not basic_row.empty:
                    cap = float(basic_row.iloc[0]['float_share']) * 10000

            # MA5
            ma5_val = None
            if not local_daily.empty:
                past5 = local_daily[local_daily['trade_date'] < td].tail(5)
                if len(past5) >= 5:
                    ma5_val = past5['close'].mean()

            # 涨幅
            if prev_close:
                pct_0945 = (price_0945 / prev_close - 1) * 100
            else:
                pct_0945 = None

            # 换手率
            if cap and cap > 0:
                turnover = vol_cum / cap * 100
            else:
                turnover = None

            # 流通市值 (亿元)
            if cap and cap > 0:
                float_mv = price_0945 * cap / 100000000
            else:
                float_mv = None

            # 量比 (分钟线volume是股, 日线vol是手 -> 统一为手)
            qrr = None
            if not local_daily.empty:
                past5 = local_daily[local_daily['trade_date'] < td].tail(5)
                if len(past5) >= 5:
                    avg_min_vol = past5['vol'].sum() / (5 * 240)
                    if avg_min_vol > 0:
                        qrr = (vol_cum / 100 / 15) / avg_min_vol

            results.append({
                'ts_code': ts_code,
                'trade_date': td,
                'limit_up_pct': round(pct, 2),
                'price_0945': round(price_0945, 3),
                'prev_close': round(prev_close, 3) if prev_close else None,
                'pct_0945': round(pct_0945, 2) if pct_0945 is not None else None,
                'vol_cum_0945': int(vol_cum),
                'qrr': round(qrr, 2) if qrr is not None else None,
                'turnover_0945': round(turnover, 2) if turnover is not None else None,
                'float_mv_yi': round(float_mv, 2) if float_mv is not None else None,
                'ma5': round(ma5_val, 3) if ma5_val else None,
                'cond_pct': 2.5 < pct_0945 < 5 if pct_0945 is not None else False,
                'cond_qrr': qrr > 1.5 if qrr is not None else False,
                'cond_turnover': turnover > 3 if turnover is not None else False,
                'cond_mv': 50 < float_mv <= 300 if float_mv is not None else False,
                'cond_ma': prev_close is not None and ma5_val is not None and prev_close > ma5_val,
            })

    print(f"\n分钟线分析完成: {len(results)} / {len(records)} 条记录")
    print(f"拉取失败: {len(failed_stocks)} 只")
    if failed_stocks:
        print(f"  失败样例: {failed_stocks[:5]}")

    return pd.DataFrame(results), failed_stocks


# ════════════════════════════════════════════════════════════════
#  3. 获取净利润并统计
# ════════════════════════════════════════════════════════════════

def add_profit_and_stats(df, pro):
    print("\n" + "=" * 60)
    print("Step 3: 获取净利润并统计")
    print("=" * 60)

    unique_codes = df['ts_code'].unique().tolist()
    print(f"需要查询净利润的股票: {len(unique_codes)}")

    profit_map = {}
    batch_size = 80
    for i in range(0, len(unique_codes), batch_size):
        batch = unique_codes[i:i+batch_size]
        try:
            fina = pro.fina_indicator(ts_code=','.join(batch),
                                      start_date='20250101', end_date='20260424',
                                      fields='ts_code,end_date,profit_dedt')
            for code, g in fina.groupby('ts_code'):
                latest = g.sort_values('end_date', ascending=False).iloc[0]
                profit_map[code] = latest['profit_dedt']
        except Exception as e:
            print(f"  批次 {i//batch_size+1} 出错: {e}")
        time.sleep(0.2)

    print(f"获取到净利润: {len(profit_map)} / {len(unique_codes)}")

    df['profit'] = df['ts_code'].map(profit_map)
    df['cond_profit'] = df['profit'] > 0
    df['all_pass'] = df['cond_pct'] & df['cond_qrr'] & df['cond_turnover'] & df['cond_mv'] & df['cond_ma'] & df['cond_profit']

    # 统计
    total = len(df)
    print(f"\n=== 统计结果 (样本数: {total}) ===")
    print(f"全部6条件通过: {df['all_pass'].sum()} ({df['all_pass'].sum()/total*100:.1f}%)")
    print()
    print("各条件通过率:")
    for col, name in [
        ('cond_pct', '涨幅2.5~5%'),
        ('cond_qrr', '量比>1.5'),
        ('cond_turnover', '换手率>3%'),
        ('cond_mv', '流通市值50~300亿'),
        ('cond_ma', '昨收>MA5'),
        ('cond_profit', '净利润>0'),
    ]:
        passed = df[col].sum()
        print(f"  {name}: {passed} / {total} ({passed/total*100:.1f}%)")

    # 按涨停日期分组
    print("\n按日期统计 (全部通过比例):")
    for td in RECENT_DATES:
        sub = df[df['trade_date'] == td]
        if not sub.empty:
            print(f"  {td}: {sub['all_pass'].sum()} / {len(sub)} ({sub['all_pass'].sum()/len(sub)*100:.1f}%)")

    # 补充名称
    names_map = {}
    for i in range(0, len(unique_codes), 100):
        batch = unique_codes[i:i+100]
        try:
            info = pro.stock_basic(ts_code=','.join(batch), fields='ts_code,name')
            for _, r in info.iterrows():
                names_map[r['ts_code']] = r['name']
        except Exception:
            pass
    df['name'] = df['ts_code'].map(names_map)

    # 保存
    out = OUTPUT_DIR / 'limit_up_0945_analysis.csv'
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f"\n详细结果已保存: {out}")

    # 保存通过的列表
    passed_df = df[df['all_pass']].copy()
    out_passed = OUTPUT_DIR / 'limit_up_0945_passed.csv'
    passed_df.to_csv(out_passed, index=False, encoding='utf-8-sig')
    print(f"通过列表已保存: {out_passed} ({len(passed_df)}条)")

    return df


# ════════════════════════════════════════════════════════════════
#  main
# ════════════════════════════════════════════════════════════════

def main():
    pro = get_tushare_pro()

    records = find_limit_up_stocks()
    df, failed = analyze_minute_data(records)

    if not df.empty:
        df = add_profit_and_stats(df, pro)

    # 汇总报告
    report = {
        'generated_at': datetime.now().isoformat(),
        'total_limit_up': len(records),
        'analyzed': len(df),
        'failed_minute': len(failed),
        'all_passed': int(df['all_pass'].sum()) if not df.empty else 0,
        'pass_rate': round(df['all_pass'].sum() / len(df) * 100, 2) if not df.empty else 0,
    }

    out_json = OUTPUT_DIR / 'limit_up_report.json'
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n汇总报告: {out_json}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
