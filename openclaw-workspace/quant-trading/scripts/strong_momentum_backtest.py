#!/usr/bin/env python3
"""
强势 momentum 策略回测

基于涨停票特征筛选:
1. close > MA5, MA10, MA20
2. MACD > 0
3. KDJ-J > 80
4. turnover_rate_f > 15%, volume_ratio > 1.5, vol/5d_avg > 1.5
5. 前3日平均涨幅 1.3%~2.0%
6. 前3日MACD持续 > 0

买入规则: 信号日(T)收盘后筛选, T+1开盘买入
卖出规则: T+1收盘 / T+3收盘 / T+5收盘
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import glob

# ── config ──────────────────────────────────────────────────────
DAILY_DIR = Path('data/daily')
DAILY_BASIC_DIR = Path('data/daily_basic')
OUTPUT_DIR = Path('outputs/intraday_0945')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 回测区间
START_DATE = '20260301'
END_DATE = '20260424'

# ════════════════════════════════════════════════════════════════
#  技术指标计算
# ════════════════════════════════════════════════════════════════

def calc_macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd = (dif - dea) * 2
    return dif, dea, macd

def calc_kdj(df, n=9):
    low_list = df['low'].rolling(window=n, min_periods=n).min()
    high_list = df['high'].rolling(window=n, min_periods=n).max()
    rsv = (df['close'] - low_list) / (high_list - low_list) * 100

    k = pd.Series(np.zeros(len(df)), index=df.index)
    d = pd.Series(np.zeros(len(df)), index=df.index)
    k.iloc[:n] = 50
    d.iloc[:n] = 50

    for i in range(n, len(df)):
        k.iloc[i] = 2/3 * k.iloc[i-1] + 1/3 * rsv.iloc[i]
        d.iloc[i] = 2/3 * d.iloc[i-1] + 1/3 * k.iloc[i]

    j = 3 * k - 2 * d
    return k, d, j

def calc_ma(close, window):
    return close.rolling(window=window).mean()

# ════════════════════════════════════════════════════════════════
#  主回测
# ════════════════════════════════════════════════════════════════

def backtest():
    print("=" * 60)
    print("强势 Momentum 策略回测")
    print("=" * 60)

    daily_files = sorted(glob.glob(str(DAILY_DIR / '*.csv')))
    print(f"总股票数: {len(daily_files)}")

    all_signals = []

    for idx, f in enumerate(daily_files):
        if idx % 500 == 0:
            print(f"  进度: {idx}/{len(daily_files)}")

        ts_code = Path(f).stem

        # 加载日线
        df_daily = pd.read_csv(f)
        if df_daily.empty or len(df_daily) < 30:
            continue
        df_daily['trade_date'] = df_daily['trade_date'].astype(str)
        df_daily = df_daily.sort_values('trade_date').reset_index(drop=True)

        # 计算技术指标
        df_daily['ma5'] = calc_ma(df_daily['close'], 5)
        df_daily['ma10'] = calc_ma(df_daily['close'], 10)
        df_daily['ma20'] = calc_ma(df_daily['close'], 20)
        df_daily['ma60'] = calc_ma(df_daily['close'], 60)

        dif, dea, macd = calc_macd(df_daily['close'])
        df_daily['dif'] = dif
        df_daily['dea'] = dea
        df_daily['macd'] = macd

        k, d, j = calc_kdj(df_daily)
        df_daily['k'] = k
        df_daily['d'] = d
        df_daily['j'] = j

        # 量能/5日均量
        df_daily['vol_ma5'] = df_daily['vol'].rolling(window=5).mean()
        df_daily['vol_ratio_5d'] = df_daily['vol'] / df_daily['vol_ma5']

        # 加载 daily_basic
        basic_path = DAILY_BASIC_DIR / f'{ts_code}.csv'
        if basic_path.exists():
            df_basic = pd.read_csv(basic_path)
            df_basic['trade_date'] = df_basic['trade_date'].astype(str)
            df_daily = df_daily.merge(
                df_basic[['trade_date', 'turnover_rate_f', 'volume_ratio', 'circ_mv']],
                on='trade_date', how='left'
            )
        else:
            df_daily['turnover_rate_f'] = np.nan
            df_daily['volume_ratio'] = np.nan
            df_daily['circ_mv'] = np.nan

        # 前N日指标 (shift)
        df_daily['t1_pct_chg'] = df_daily['pct_chg'].shift(1)
        df_daily['t2_pct_chg'] = df_daily['pct_chg'].shift(2)
        df_daily['t3_pct_chg'] = df_daily['pct_chg'].shift(3)
        df_daily['t1_macd'] = df_daily['macd'].shift(1)
        df_daily['t2_macd'] = df_daily['macd'].shift(2)
        df_daily['t3_macd'] = df_daily['macd'].shift(3)
        df_daily['avg_3d_pct'] = (df_daily['t1_pct_chg'] + df_daily['t2_pct_chg'] + df_daily['t3_pct_chg']) / 3

        # 筛选回测区间
        mask = (df_daily['trade_date'] >= START_DATE) & (df_daily['trade_date'] <= END_DATE)
        df_test = df_daily[mask].copy()

        if df_test.empty:
            continue

        # 条件筛选
        cond1 = (df_test['close'] > df_test['ma5']) & (df_test['close'] > df_test['ma10']) & (df_test['close'] > df_test['ma20'])
        cond2 = df_test['macd'] > 0
        cond3 = df_test['j'] > 80
        cond4 = (df_test['turnover_rate_f'] > 15) & (df_test['volume_ratio'] > 1.5) & (df_test['vol_ratio_5d'] > 1.5)
        cond5 = (df_test['avg_3d_pct'] >= 1.3) & (df_test['avg_3d_pct'] <= 2.0)
        cond6 = (df_test['t1_macd'] > 0) & (df_test['t2_macd'] > 0) & (df_test['t3_macd'] > 0)

        signal = df_test[cond1 & cond2 & cond3 & cond4 & cond5 & cond6].copy()

        if signal.empty:
            continue

        # 计算收益 (需要找到信号日的下一天、第三天、第五天)
        for _, row in signal.iterrows():
            td = row['trade_date']
            td_idx = df_daily[df_daily['trade_date'] == td].index
            if len(td_idx) == 0:
                continue
            td_idx = td_idx[0]

            # T+1数据
            if td_idx + 1 >= len(df_daily):
                continue
            t1 = df_daily.iloc[td_idx + 1]

            # T+3数据
            t3_ret = None
            if td_idx + 3 < len(df_daily):
                t3 = df_daily.iloc[td_idx + 3]
                t3_ret = (t3['close'] / t1['open'] - 1) * 100

            # T+5数据
            t5_ret = None
            if td_idx + 5 < len(df_daily):
                t5 = df_daily.iloc[td_idx + 5]
                t5_ret = (t5['close'] / t1['open'] - 1) * 100

            all_signals.append({
                'ts_code': ts_code,
                'signal_date': td,
                'buy_price': t1['open'],
                't1_close': t1['close'],
                't1_high': t1['high'],
                't1_low': t1['low'],
                'return_1d': (t1['close'] / t1['open'] - 1) * 100,
                'return_3d': t3_ret,
                'return_5d': t5_ret,
                'limit_up_next': t1['pct_chg'] >= 9.5,
                # 信号日指标
                'close': row['close'],
                'macd': row['macd'],
                'j': row['j'],
                'turnover_rate_f': row['turnover_rate_f'],
                'volume_ratio': row['volume_ratio'],
                'vol_ratio_5d': row['vol_ratio_5d'],
                'avg_3d_pct': row['avg_3d_pct'],
                'circ_mv': row['circ_mv'],
            })

    df_signals = pd.DataFrame(all_signals)
    return df_signals


def analyze_results(df):
    print("\n" + "=" * 60)
    print("回测结果统计")
    print("=" * 60)

    if df.empty:
        print("无信号!")
        return

    print(f"\n总信号数: {len(df)}")
    print(f"涉及交易日: {df['signal_date'].nunique()}")
    by_date = df.groupby('signal_date').size()
    print(f"平均每天信号: {by_date.mean():.1f}")
    print(f"信号最多一天: {by_date.idxmax()} ({by_date.max()}只)")

    # 次日收益
    r1 = df['return_1d'].dropna()
    print(f"\n--- T+1开盘买, T+1收盘卖 ---")
    print(f"交易次数: {len(r1)}")
    print(f"平均收益: {r1.mean():.2f}%")
    print(f"中位数: {r1.median():.2f}%")
    print(f"胜率(>0): {(r1 > 0).mean()*100:.1f}%")
    print(f"涨停比例(≥9.5%): {(r1 >= 9.5).mean()*100:.1f}%")
    print(f"亏损比例(<0): {(r1 < 0).mean()*100:.1f}%")
    print(f"大亏比例(<-5%): {(r1 < -5).mean()*100:.1f}%")
    print(f"最大单笔盈利: {r1.max():.2f}%")
    print(f"最大单笔亏损: {r1.min():.2f}%")

    # T+3
    r3 = df['return_3d'].dropna()
    if len(r3) > 0:
        print(f"\n--- T+1开盘买, T+3收盘卖 ---")
        print(f"交易次数: {len(r3)}")
        print(f"平均收益: {r3.mean():.2f}%")
        print(f"中位数: {r3.median():.2f}%")
        print(f"胜率(>0): {(r3 > 0).mean()*100:.1f}%")

    # T+5
    r5 = df['return_5d'].dropna()
    if len(r5) > 0:
        print(f"\n--- T+1开盘买, T+5收盘卖 ---")
        print(f"交易次数: {len(r5)}")
        print(f"平均收益: {r5.mean():.2f}%")
        print(f"中位数: {r5.median():.2f}%")
        print(f"胜率(>0): {(r5 > 0).mean()*100:.1f}%")

    # 按日期统计次日平均收益
    print(f"\n--- 按日期统计(T+1) ---")
    by_date_ret = df.groupby('signal_date')['return_1d'].agg(['mean', 'count', 'sum'])
    by_date_ret = by_date_ret[by_date_ret['count'] > 0]
    print(f"有信号天数: {len(by_date_ret)}")
    print(f"日均收益: {by_date_ret['mean'].mean():.2f}%")
    print(f"正收益天数: {(by_date_ret['mean'] > 0).sum()} / {len(by_date_ret)}")

    # 保存
    out = OUTPUT_DIR / 'strong_momentum_signals.csv'
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f"\n详细信号已保存: {out}")

    return df


def generate_charts(df):
    if df.empty:
        return

    print("\n生成图表...")
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.rcParams['font.family'] = ['SimSong', 'Hei', 'LiHei Pro', 'Arial Unicode MS', 'sans-serif']
    matplotlib.rcParams['axes.unicode_minus'] = False

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))

    r1 = df['return_1d'].dropna()
    r3 = df['return_3d'].dropna()
    r5 = df['return_5d'].dropna()

    # 1. T+1收益分布
    ax = axes[0, 0]
    ax.hist(r1, bins=50, color='steelblue', edgecolor='white')
    ax.axvline(r1.mean(), color='red', linestyle='--', label=f'均值: {r1.mean():.2f}%')
    ax.axvline(r1.median(), color='green', linestyle='--', label=f'中位数: {r1.median():.2f}%')
    ax.axvline(0, color='black', linestyle='-', linewidth=1)
    ax.set_title('T+1收益分布')
    ax.set_xlabel('收益率 (%)')
    ax.legend()

    # 2. T+1/T+3/T+5 累计分布
    ax = axes[0, 1]
    for ret, label, color in [(r1, 'T+1', 'steelblue'), (r3, 'T+3', 'coral'), (r5, 'T+5', 'green')]:
        if len(ret) > 0:
            sorted_ret = ret.sort_values()
            cum_prob = np.arange(1, len(sorted_ret)+1) / len(sorted_ret) * 100
            ax.plot(sorted_ret.values, cum_prob, label=f'{label} (胜率={(ret>0).mean()*100:.0f}%)', linewidth=2)
    ax.axvline(0, color='black', linestyle='-', linewidth=1)
    ax.set_title('累计收益分布')
    ax.set_xlabel('收益率 (%)')
    ax.set_ylabel('累计比例 (%)')
    ax.legend()

    # 3. 每日平均收益
    ax = axes[0, 2]
    by_date = df.groupby('signal_date')['return_1d'].mean()
    ax.bar(range(len(by_date)), by_date.values, color=['green' if x > 0 else 'red' for x in by_date.values])
    ax.axhline(0, color='black', linestyle='-', linewidth=1)
    ax.set_title('每日平均T+1收益')
    ax.set_xticks(range(0, len(by_date), max(1, len(by_date)//10)))
    ax.set_xticklabels([by_date.index[i] for i in range(0, len(by_date), max(1, len(by_date)//10))], rotation=45)

    # 4. 信号数量按日期
    ax = axes[1, 0]
    by_date_cnt = df.groupby('signal_date').size()
    ax.bar(range(len(by_date_cnt)), by_date_cnt.values, color='lightblue')
    ax.set_title('每日信号数量')
    ax.set_xticks(range(0, len(by_date_cnt), max(1, len(by_date_cnt)//10)))
    ax.set_xticklabels([by_date_cnt.index[i] for i in range(0, len(by_date_cnt), max(1, len(by_date_cnt)//10))], rotation=45)

    # 5. 收益 vs J值
    ax = axes[1, 1]
    valid = df[df['j'].notna() & df['return_1d'].notna()]
    ax.scatter(valid['j'], valid['return_1d'], alpha=0.3, s=15)
    ax.axhline(0, color='black', linestyle='-', linewidth=1)
    ax.set_xlabel('J值')
    ax.set_ylabel('T+1收益')
    ax.set_title('J值 vs T+1收益')

    # 6. 收益 vs 换手率
    ax = axes[1, 2]
    valid = df[df['turnover_rate_f'].notna() & df['return_1d'].notna()]
    ax.scatter(valid['turnover_rate_f'], valid['return_1d'], alpha=0.3, s=15)
    ax.axhline(0, color='black', linestyle='-', linewidth=1)
    ax.set_xlabel('换手率 (%)')
    ax.set_ylabel('T+1收益')
    ax.set_title('换手率 vs T+1收益')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'strong_momentum_backtest.png', dpi=150, bbox_inches='tight')
    print("图表已保存: outputs/intraday_0945/strong_momentum_backtest.png")


def main():
    df = backtest()
    df = analyze_results(df)
    generate_charts(df)

    # 汇总
    report = {
        'generated_at': datetime.now().isoformat(),
        'total_signals': len(df),
        'trading_days': df['signal_date'].nunique() if not df.empty else 0,
    }
    if not df.empty:
        r1 = df['return_1d'].dropna()
        report['win_rate_1d'] = round((r1 > 0).mean() * 100, 2)
        report['avg_return_1d'] = round(r1.mean(), 2)
        r3 = df['return_3d'].dropna()
        if len(r3) > 0:
            report['win_rate_3d'] = round((r3 > 0).mean() * 100, 2)
            report['avg_return_3d'] = round(r3.mean(), 2)

    with open(OUTPUT_DIR / 'strong_momentum_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n汇总报告: {OUTPUT_DIR / 'strong_momentum_report.json'}")


if __name__ == '__main__':
    main()
