#!/usr/bin/env python3
"""
强势 momentum 策略回测 V2 (优化版)

优化方向:
1. 前3日平均涨幅 > 0% (放宽)
2. 换手率 > 8% (降低)
3. J值 50~80 (准强势, 非超买)
4. 前1日J值 < 50 (刚进入强势区)

买入: 信号日(T)收盘后筛选, T+1开盘买入
卖出: T+1收盘 / T+3收盘 / T+5收盘
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
    print("强势 Momentum V2 回测")
    print("=" * 60)

    daily_files = sorted(glob.glob(str(DAILY_DIR / '*.csv')))
    print(f"总股票数: {len(daily_files)}")

    all_signals = []

    for idx, f in enumerate(daily_files):
        if idx % 500 == 0:
            print(f"  进度: {idx}/{len(daily_files)}")

        ts_code = Path(f).stem
        df_daily = pd.read_csv(f)
        if df_daily.empty or len(df_daily) < 30:
            continue
        df_daily['trade_date'] = df_daily['trade_date'].astype(str)
        df_daily = df_daily.sort_values('trade_date').reset_index(drop=True)

        # 技术指标
        df_daily['ma5'] = calc_ma(df_daily['close'], 5)
        df_daily['ma10'] = calc_ma(df_daily['close'], 10)
        df_daily['ma20'] = calc_ma(df_daily['close'], 20)

        dif, dea, macd = calc_macd(df_daily['close'])
        df_daily['dif'] = dif
        df_daily['dea'] = dea
        df_daily['macd'] = macd

        k, d, j = calc_kdj(df_daily)
        df_daily['k'] = k
        df_daily['d'] = d
        df_daily['j'] = j

        df_daily['vol_ma5'] = df_daily['vol'].rolling(window=5).mean()
        df_daily['vol_ratio_5d'] = df_daily['vol'] / df_daily['vol_ma5']

        # daily_basic
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

        # 前N日指标
        df_daily['t1_pct_chg'] = df_daily['pct_chg'].shift(1)
        df_daily['t2_pct_chg'] = df_daily['pct_chg'].shift(2)
        df_daily['t3_pct_chg'] = df_daily['pct_chg'].shift(3)
        df_daily['t1_macd'] = df_daily['macd'].shift(1)
        df_daily['t2_macd'] = df_daily['macd'].shift(2)
        df_daily['t3_macd'] = df_daily['macd'].shift(3)
        df_daily['t1_j'] = df_daily['j'].shift(1)
        df_daily['avg_3d_pct'] = (df_daily['t1_pct_chg'] + df_daily['t2_pct_chg'] + df_daily['t3_pct_chg']) / 3

        mask = (df_daily['trade_date'] >= START_DATE) & (df_daily['trade_date'] <= END_DATE)
        df_test = df_daily[mask].copy()
        if df_test.empty:
            continue

        # V2 条件
        cond1 = (df_test['close'] > df_test['ma5']) & (df_test['close'] > df_test['ma10']) & (df_test['close'] > df_test['ma20'])
        cond2 = df_test['macd'] > 0
        cond3 = (df_test['j'] >= 50) & (df_test['j'] <= 80)  # 准强势
        cond4 = (df_test['turnover_rate_f'] > 8) & (df_test['volume_ratio'] > 1.5) & (df_test['vol_ratio_5d'] > 1.5)
        cond5 = df_test['avg_3d_pct'] > 0  # 放宽
        cond6 = (df_test['t1_macd'] > 0) & (df_test['t2_macd'] > 0) & (df_test['t3_macd'] > 0)
        cond7 = df_test['t1_j'] < 50  # 刚进入强势区

        signal = df_test[cond1 & cond2 & cond3 & cond4 & cond5 & cond6 & cond7].copy()
        if signal.empty:
            continue

        for _, row in signal.iterrows():
            td = row['trade_date']
            td_idx = df_daily[df_daily['trade_date'] == td].index
            if len(td_idx) == 0:
                continue
            td_idx = td_idx[0]

            if td_idx + 1 >= len(df_daily):
                continue
            t1 = df_daily.iloc[td_idx + 1]

            t3_ret = None
            if td_idx + 3 < len(df_daily):
                t3 = df_daily.iloc[td_idx + 3]
                t3_ret = (t3['close'] / t1['open'] - 1) * 100

            t5_ret = None
            if td_idx + 5 < len(df_daily):
                t5 = df_daily.iloc[td_idx + 5]
                t5_ret = (t5['close'] / t1['open'] - 1) * 100

            all_signals.append({
                'ts_code': ts_code,
                'signal_date': td,
                'buy_price': t1['open'],
                't1_close': t1['close'],
                'return_1d': (t1['close'] / t1['open'] - 1) * 100,
                'return_3d': t3_ret,
                'return_5d': t5_ret,
                'limit_up_next': t1['pct_chg'] >= 9.5,
                'close': row['close'],
                'macd': row['macd'],
                'j': row['j'],
                't1_j': row['t1_j'],
                'turnover_rate_f': row['turnover_rate_f'],
                'volume_ratio': row['volume_ratio'],
                'vol_ratio_5d': row['vol_ratio_5d'],
                'avg_3d_pct': row['avg_3d_pct'],
                'circ_mv': row['circ_mv'],
            })

    return pd.DataFrame(all_signals)


def analyze(df):
    print("\n" + "=" * 60)
    print("V2 回测结果")
    print("=" * 60)

    if df.empty:
        print("无信号!")
        return

    print(f"\n总信号: {len(df)}")
    print(f"交易日: {df['signal_date'].nunique()}")
    by_date = df.groupby('signal_date').size()
    print(f"日均信号: {by_date.mean():.1f}")

    r1 = df['return_1d'].dropna()
    print(f"\n--- T+1 ---")
    print(f"次数: {len(r1)}, 均值: {r1.mean():.2f}%, 中位数: {r1.median():.2f}%")
    print(f"胜率: {(r1>0).mean()*100:.1f}%, 涨停: {(r1>=9.5).mean()*100:.1f}%, 大亏: {(r1<-5).mean()*100:.1f}%")

    r3 = df['return_3d'].dropna()
    if len(r3):
        print(f"\n--- T+3 ---")
        print(f"次数: {len(r3)}, 均值: {r3.mean():.2f}%, 中位数: {r3.median():.2f}%, 胜率: {(r3>0).mean()*100:.1f}%")

    r5 = df['return_5d'].dropna()
    if len(r5):
        print(f"\n--- T+5 ---")
        print(f"次数: {len(r5)}, 均值: {r5.mean():.2f}%, 中位数: {r5.median():.2f}%, 胜率: {(r5>0).mean()*100:.1f}%")

    out = OUTPUT_DIR / 'strong_momentum_v2_signals.csv'
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f"\n已保存: {out}")
    return df


def charts(df):
    if df.empty:
        return
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.rcParams['font.family'] = ['SimSong', 'Hei', 'LiHei Pro', 'Arial Unicode MS', 'sans-serif']
    matplotlib.rcParams['axes.unicode_minus'] = False

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    r1 = df['return_1d'].dropna()
    r3 = df['return_3d'].dropna()
    r5 = df['return_5d'].dropna()

    # T+1分布
    ax = axes[0, 0]
    ax.hist(r1, bins=40, color='steelblue', edgecolor='white')
    ax.axvline(r1.mean(), color='red', linestyle='--', label=f'均值: {r1.mean():.2f}%')
    ax.axvline(0, color='black', linewidth=1)
    ax.set_title('T+1收益分布')
    ax.legend()

    # 累计分布
    ax = axes[0, 1]
    for ret, label, color in [(r1, 'T+1', 'steelblue'), (r3, 'T+3', 'coral'), (r5, 'T+5', 'green')]:
        if len(ret):
            s = ret.sort_values()
            ax.plot(s.values, np.arange(1, len(s)+1)/len(s)*100, label=f'{label} ({(ret>0).mean()*100:.0f}%)', linewidth=2)
    ax.axvline(0, color='black', linewidth=1)
    ax.set_title('累计收益分布')
    ax.set_xlabel('收益率 (%)')
    ax.set_ylabel('累计比例 (%)')
    ax.legend()

    # 每日平均
    ax = axes[0, 2]
    by_date = df.groupby('signal_date')['return_1d'].mean()
    ax.bar(range(len(by_date)), by_date.values, color=['green' if x>0 else 'red' for x in by_date.values])
    ax.axhline(0, color='black', linewidth=1)
    ax.set_title('每日平均T+1收益')
    ax.set_xticks(range(0, len(by_date), max(1, len(by_date)//10)))
    ax.set_xticklabels([by_date.index[i] for i in range(0, len(by_date), max(1, len(by_date)//10))], rotation=45)

    # 信号数
    ax = axes[1, 0]
    by_date_cnt = df.groupby('signal_date').size()
    ax.bar(range(len(by_date_cnt)), by_date_cnt.values, color='lightblue')
    ax.set_title('每日信号数量')
    ax.set_xticks(range(0, len(by_date_cnt), max(1, len(by_date_cnt)//10)))
    ax.set_xticklabels([by_date_cnt.index[i] for i in range(0, len(by_date_cnt), max(1, len(by_date_cnt)//10))], rotation=45)

    # J值 vs 收益
    ax = axes[1, 1]
    valid = df[df['j'].notna() & df['return_1d'].notna()]
    ax.scatter(valid['j'], valid['return_1d'], alpha=0.3, s=15)
    ax.axhline(0, color='black', linewidth=1)
    ax.set_xlabel('J值')
    ax.set_ylabel('T+1收益')
    ax.set_title('J值 vs T+1收益')

    # 换手率 vs 收益
    ax = axes[1, 2]
    valid = df[df['turnover_rate_f'].notna() & df['return_1d'].notna()]
    ax.scatter(valid['turnover_rate_f'], valid['return_1d'], alpha=0.3, s=15)
    ax.axhline(0, color='black', linewidth=1)
    ax.set_xlabel('换手率 (%)')
    ax.set_ylabel('T+1收益')
    ax.set_title('换手率 vs T+1收益')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'strong_momentum_v2_backtest.png', dpi=150, bbox_inches='tight')
    print("图表: outputs/intraday_0945/strong_momentum_v2_backtest.png")


def main():
    df = backtest()
    df = analyze(df)
    charts(df)

if __name__ == '__main__':
    main()
