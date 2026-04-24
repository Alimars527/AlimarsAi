#!/usr/bin/env python3
"""
涨停票技术指标分析

分析近半个月涨停票在涨停当天的MACD、KDJ、成交量、换手率、量比、涨幅，
以及前1-3日的日线状态。
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

# ── config ──────────────────────────────────────────────────────
RECENT_DATES = ['20260410','20260413','20260414','20260415','20260416',
                '20260417','20260420','20260421','20260422','20260423','20260424']
DAILY_DIR = Path('data/daily')
DAILY_BASIC_DIR = Path('data/daily_basic')
OUTPUT_DIR = Path('outputs/intraday_0945')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ════════════════════════════════════════════════════════════════
#  技术指标计算
# ════════════════════════════════════════════════════════════════

def calc_macd(df: pd.DataFrame, fast=12, slow=26, signal=9):
    """计算MACD指标"""
    close = df['close']
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd = (dif - dea) * 2
    return dif, dea, macd

def calc_kdj(df: pd.DataFrame, n=9, m1=3, m2=3):
    """计算KDJ指标"""
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
    return k, d, j, rsv

def calc_ma(df: pd.DataFrame, windows=[5, 10, 20, 60]):
    """计算多条均线"""
    mas = {}
    for w in windows:
        mas[f'ma{w}'] = df['close'].rolling(window=w).mean()
    return mas

# ════════════════════════════════════════════════════════════════
#  主分析
# ════════════════════════════════════════════════════════════════

def analyze_limit_up_indicators():
    print("=" * 60)
    print("涨停票技术指标分析")
    print("=" * 60)

    # 1. 找出涨停票
    records = []
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

    # 2. 逐只分析
    results = []
    failed = []

    for idx, (ts_code, td, pct) in enumerate(records):
        if idx % 100 == 0:
            print(f"  进度: {idx}/{len(records)}")

        # 加载日线数据
        daily_path = DAILY_DIR / f'{ts_code}.csv'
        basic_path = DAILY_BASIC_DIR / f'{ts_code}.csv'

        if not daily_path.exists():
            failed.append((ts_code, td, 'no_daily'))
            continue

        df_daily = pd.read_csv(daily_path)
        df_daily['trade_date'] = df_daily['trade_date'].astype(str)
        df_daily = df_daily.sort_values('trade_date').reset_index(drop=True)

        # 找到涨停日索引
        target_idx = df_daily[df_daily['trade_date'] == td].index
        if len(target_idx) == 0:
            failed.append((ts_code, td, 'not_found'))
            continue
        target_idx = target_idx[0]

        # 需要至少60天历史数据计算MA60和MACD
        if target_idx < 60:
            failed.append((ts_code, td, 'insufficient_history'))
            continue

        # 计算技术指标
        dif, dea, macd = calc_macd(df_daily)
        k, d, j, rsv = calc_kdj(df_daily)
        mas = calc_ma(df_daily)

        # 涨停当天数据
        curr = df_daily.iloc[target_idx]
        curr_macd = macd.iloc[target_idx]
        curr_dif = dif.iloc[target_idx]
        curr_dea = dea.iloc[target_idx]
        curr_k = k.iloc[target_idx]
        curr_d = d.iloc[target_idx]
        curr_j = j.iloc[target_idx]
        curr_rsv = rsv.iloc[target_idx]

        # 前1-3日数据
        prev_data = {}
        for i in range(1, 4):
            if target_idx - i >= 0:
                prev = df_daily.iloc[target_idx - i]
                prev_data[f't{i}'] = {
                    'trade_date': prev['trade_date'],
                    'close': prev['close'],
                    'pct_chg': prev['pct_chg'],
                    'vol': prev['vol'],
                    'open': prev['open'],
                    'high': prev['high'],
                    'low': prev['low'],
                    'macd': macd.iloc[target_idx - i],
                    'dif': dif.iloc[target_idx - i],
                    'k': k.iloc[target_idx - i],
                    'd': d.iloc[target_idx - i],
                    'j': j.iloc[target_idx - i],
                    'ma5': mas['ma5'].iloc[target_idx - i],
                    'ma10': mas['ma10'].iloc[target_idx - i],
                    'ma20': mas['ma20'].iloc[target_idx - i],
                    'ma60': mas['ma60'].iloc[target_idx - i],
                }

        # 当日均线位置
        curr_ma5 = mas['ma5'].iloc[target_idx]
        curr_ma10 = mas['ma10'].iloc[target_idx]
        curr_ma20 = mas['ma20'].iloc[target_idx]
        curr_ma60 = mas['ma60'].iloc[target_idx]

        # 加载basic数据 (换手率、量比)
        turnover_rate_f = None
        volume_ratio = None
        circ_mv = None
        if basic_path.exists():
            df_basic = pd.read_csv(basic_path)
            df_basic['trade_date'] = df_basic['trade_date'].astype(str)
            basic_row = df_basic[df_basic['trade_date'] == td]
            if not basic_row.empty:
                turnover_rate_f = float(basic_row.iloc[0]['turnover_rate_f']) if pd.notna(basic_row.iloc[0]['turnover_rate_f']) else None
                volume_ratio = float(basic_row.iloc[0]['volume_ratio']) if pd.notna(basic_row.iloc[0]['volume_ratio']) else None
                circ_mv = float(basic_row.iloc[0]['circ_mv']) if pd.notna(basic_row.iloc[0]['circ_mv']) else None

        # 量能变化 (当日vol / 前5日平均vol)
        vol_ratio = None
        if target_idx >= 5:
            avg_vol_5 = df_daily.iloc[target_idx-5:target_idx]['vol'].mean()
            if avg_vol_5 > 0:
                vol_ratio = curr['vol'] / avg_vol_5

        # 封装结果
        record = {
            'ts_code': ts_code,
            'trade_date': td,
            'name': '',  # 后面补充
            'limit_up_pct': pct,

            # 涨停当天
            'open': curr['open'],
            'high': curr['high'],
            'low': curr['low'],
            'close': curr['close'],
            'pre_close': curr['pre_close'],
            'vol': curr['vol'],
            'amount': curr['amount'],
            'turnover_rate_f': turnover_rate_f,
            'volume_ratio': volume_ratio,
            'circ_mv': circ_mv,
            'vol_ratio_5d': vol_ratio,

            # 技术指标
            'macd': curr_macd,
            'dif': curr_dif,
            'dea': curr_dea,
            'k': curr_k,
            'd': curr_d,
            'j': curr_j,
            'rsv': curr_rsv,

            # 均线
            'ma5': curr_ma5,
            'ma10': curr_ma10,
            'ma20': curr_ma20,
            'ma60': curr_ma60,
            'close_above_ma5': curr['close'] > curr_ma5 if pd.notna(curr_ma5) else None,
            'close_above_ma10': curr['close'] > curr_ma10 if pd.notna(curr_ma10) else None,
            'close_above_ma20': curr['close'] > curr_ma20 if pd.notna(curr_ma20) else None,
            'close_above_ma60': curr['close'] > curr_ma60 if pd.notna(curr_ma60) else None,

            # MACD状态
            'macd_positive': curr_macd > 0 if pd.notna(curr_macd) else None,
            'dif_above_dea': curr_dif > curr_dea if pd.notna(curr_dif) and pd.notna(curr_dea) else None,
            'macd_golden_cross': False,  # 后面计算
            'macd_dead_cross': False,
        }

        # 判断MACD金叉/死叉 (近3日内)
        if target_idx >= 3:
            for i in range(1, 4):
                if dif.iloc[target_idx-i] < dea.iloc[target_idx-i] and dif.iloc[target_idx-i+1] > dea.iloc[target_idx-i+1]:
                    record['macd_golden_cross'] = True
                if dif.iloc[target_idx-i] > dea.iloc[target_idx-i] and dif.iloc[target_idx-i+1] < dea.iloc[target_idx-i+1]:
                    record['macd_dead_cross'] = True

        # 前1-3日数据
        for prefix, data in prev_data.items():
            for key, val in data.items():
                record[f'{prefix}_{key}'] = val

        results.append(record)

    print(f"\n分析完成: {len(results)} / {len(records)} 条记录")
    print(f"失败: {len(failed)} 条")

    return pd.DataFrame(results), failed


def add_names_and_save(df):
    print("\n补充股票名称...")
    import tushare as ts
    from quant.config import load_settings

    settings = load_settings()
    pro = ts.pro_api(settings.get('tushare_token'))

    unique_codes = df['ts_code'].unique().tolist()
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

    out = OUTPUT_DIR / 'limit_up_indicators.csv'
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f"数据已保存: {out}")
    return df


def print_statistics(df):
    print("\n" + "=" * 60)
    print("涨停票技术指标统计")
    print("=" * 60)

    print(f"\n样本数: {len(df)}")

    # 涨停当天指标
    print("\n--- 涨停当天指标 ---")
    for col, name in [
        ('turnover_rate_f', '换手率(%)'),
        ('volume_ratio', '量比'),
        ('vol_ratio_5d', '量能/5日均量'),
        ('limit_up_pct', '涨停涨幅(%)'),
    ]:
        vals = pd.to_numeric(df[col], errors='coerce').dropna()
        if len(vals) > 0:
            print(f"{name}: 均值={vals.mean():.2f}, 中位数={vals.median():.2f}, "
                  f"P25={vals.quantile(0.25):.2f}, P75={vals.quantile(0.75):.2f}")

    print("\n--- MACD ---")
    macd_pos = df['macd_positive'].sum()
    dif_dea = df['dif_above_dea'].sum()
    gc = df['macd_golden_cross'].sum()
    print(f"MACD>0: {macd_pos}/{len(df)} ({macd_pos/len(df)*100:.1f}%)")
    print(f"DIF>DEA: {dif_dea}/{len(df)} ({dif_dea/len(df)*100:.1f}%)")
    print(f"近3日MACD金叉: {gc}/{len(df)} ({gc/len(df)*100:.1f}%)")

    for col, name in [('macd', 'MACD'), ('dif', 'DIF'), ('dea', 'DEA')]:
        vals = pd.to_numeric(df[col], errors='coerce').dropna()
        print(f"{name}: 均值={vals.mean():.3f}, 中位数={vals.median():.3f}")

    print("\n--- KDJ ---")
    for col, name in [('k', 'K'), ('d', 'D'), ('j', 'J')]:
        vals = pd.to_numeric(df[col], errors='coerce').dropna()
        print(f"{name}: 均值={vals.mean():.1f}, 中位数={vals.median():.1f}, "
              f"P25={vals.quantile(0.25):.1f}, P75={vals.quantile(0.75):.1f}")

    j_high = (df['j'] > 80).sum()
    j_low = (df['j'] < 20).sum()
    print(f"J>80(超买): {j_high}/{len(df)} ({j_high/len(df)*100:.1f}%)")
    print(f"J<20(超卖): {j_low}/{len(df)} ({j_low/len(df)*100:.1f}%)")

    print("\n--- 均线位置 ---")
    for col, name in [
        ('close_above_ma5', '收盘价>MA5'),
        ('close_above_ma10', '收盘价>MA10'),
        ('close_above_ma20', '收盘价>MA20'),
        ('close_above_ma60', '收盘价>MA60'),
    ]:
        cnt = df[col].sum()
        print(f"{name}: {cnt}/{len(df)} ({cnt/len(df)*100:.1f}%)")

    print("\n--- 前1-3日涨幅 ---")
    for t in ['t1', 't2', 't3']:
        col = f'{t}_pct_chg'
        vals = pd.to_numeric(df[col], errors='coerce').dropna()
        if len(vals) > 0:
            pos = (vals > 0).sum()
            print(f"{t}(前{t[-1]}日): 均值={vals.mean():.2f}%, 中位数={vals.median():.2f}%, "
                  f"上涨比例={pos/len(vals)*100:.1f}%")

    print("\n--- 前1-3日MACD ---")
    for t in ['t1', 't2', 't3']:
        col = f'{t}_macd'
        vals = pd.to_numeric(df[col], errors='coerce').dropna()
        pos = (vals > 0).sum()
        print(f"{t} MACD>0: {pos}/{len(vals)} ({pos/len(vals)*100:.1f}%)")

    print("\n--- 前1-3日J值 ---")
    for t in ['t1', 't2', 't3']:
        col = f'{t}_j'
        vals = pd.to_numeric(df[col], errors='coerce').dropna()
        j_high = (vals > 80).sum()
        j_low = (vals < 20).sum()
        print(f"{t} J>80: {j_high}/{len(vals)} ({j_high/len(vals)*100:.1f}%), "
              f"J<20: {j_low}/{len(vals)} ({j_low/len(vals)*100:.1f}%)")


def generate_charts(df):
    print("\n生成图表...")
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.rcParams['font.family'] = ['SimSong', 'Hei', 'LiHei Pro', 'Arial Unicode MS', 'sans-serif']
    matplotlib.rcParams['axes.unicode_minus'] = False

    fig, axes = plt.subplots(3, 3, figsize=(16, 14))

    # 1. 换手率分布
    ax = axes[0, 0]
    vals = pd.to_numeric(df['turnover_rate_f'], errors='coerce').dropna()
    ax.hist(vals, bins=50, color='steelblue', edgecolor='white')
    ax.axvline(vals.median(), color='red', linestyle='--', label=f'中位数: {vals.median():.1f}%')
    ax.set_title('涨停当天换手率分布')
    ax.set_xlabel('换手率 (%)')
    ax.legend()

    # 2. 量比分布
    ax = axes[0, 1]
    vals = pd.to_numeric(df['volume_ratio'], errors='coerce').dropna()
    ax.hist(vals, bins=50, color='coral', edgecolor='white')
    ax.axvline(vals.median(), color='red', linestyle='--', label=f'中位数: {vals.median():.1f}')
    ax.set_title('涨停当天量比分布')
    ax.set_xlabel('量比')
    ax.legend()

    # 3. 量能/5日均量
    ax = axes[0, 2]
    vals = pd.to_numeric(df['vol_ratio_5d'], errors='coerce').dropna()
    vals = vals[vals < 10]  # 剔除极端值
    ax.hist(vals, bins=50, color='green', edgecolor='white', alpha=0.7)
    ax.axvline(vals.median(), color='red', linestyle='--', label=f'中位数: {vals.median():.1f}')
    ax.set_title('量能/5日均量分布')
    ax.set_xlabel('倍数')
    ax.legend()

    # 4. MACD分布
    ax = axes[1, 0]
    vals = pd.to_numeric(df['macd'], errors='coerce').dropna()
    ax.hist(vals, bins=50, color='purple', edgecolor='white', alpha=0.7)
    ax.axvline(0, color='black', linestyle='-', linewidth=1)
    ax.axvline(vals.median(), color='red', linestyle='--', label=f'中位数: {vals.median():.2f}')
    ax.set_title('涨停当天MACD分布')
    ax.set_xlabel('MACD')
    ax.legend()

    # 5. J值分布
    ax = axes[1, 1]
    vals = pd.to_numeric(df['j'], errors='coerce').dropna()
    vals = vals[(vals > -50) & (vals < 150)]  # 剔除极端值
    ax.hist(vals, bins=50, color='orange', edgecolor='white')
    ax.axvline(80, color='red', linestyle=':', label='超买线80')
    ax.axvline(20, color='green', linestyle=':', label='超卖线20')
    ax.axvline(vals.median(), color='blue', linestyle='--', label=f'中位数: {vals.median():.1f}')
    ax.set_title('涨停当天KDJ-J分布')
    ax.set_xlabel('J值')
    ax.legend()

    # 6. 均线多头排列比例
    ax = axes[1, 2]
    conditions = ['close_above_ma5', 'close_above_ma10', 'close_above_ma20', 'close_above_ma60']
    labels = ['MA5', 'MA10', 'MA20', 'MA60']
    rates = [df[c].mean() * 100 for c in conditions]
    colors = ['#51cf66', '#51cf66', '#51cf66', '#51cf66']
    bars = ax.bar(labels, rates, color=colors)
    ax.set_ylim(0, 110)
    ax.set_title('收盘价在均线上方比例')
    ax.set_ylabel('比例 (%)')
    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, f'{rate:.1f}%', ha='center')

    # 7. 前3日涨幅趋势
    ax = axes[2, 0]
    for t, color in [('t3', 'lightblue'), ('t2', 'steelblue'), ('t1', 'darkblue')]:
        vals = pd.to_numeric(df[f'{t}_pct_chg'], errors='coerce').dropna()
        vals = vals[(vals > -10) & (vals < 10)]
        ax.hist(vals, bins=40, alpha=0.5, color=color, label=f'前{t[-1]}日')
    ax.axvline(0, color='black', linestyle='-', linewidth=1)
    ax.set_title('前1-3日涨幅分布')
    ax.set_xlabel('涨幅 (%)')
    ax.legend()

    # 8. MACD金叉/死叉比例
    ax = axes[2, 1]
    gc = df['macd_golden_cross'].sum()
    dc = df['macd_dead_cross'].sum()
    neither = len(df) - gc - dc
    ax.pie([gc, dc, neither], labels=['金叉', '死叉', '无'], autopct='%1.1f%%',
           colors=['#51cf66', '#ff6b6b', '#dee2e6'])
    ax.set_title('近3日MACD交叉状态')

    # 9. 前1日J值 vs 当日J值
    ax = axes[2, 2]
    t1_j = pd.to_numeric(df['t1_j'], errors='coerce').dropna()
    curr_j = pd.to_numeric(df['j'], errors='coerce').dropna()
    # 对齐索引
    valid_idx = df.index[df['t1_j'].notna() & df['j'].notna()]
    ax.scatter(df.loc[valid_idx, 't1_j'], df.loc[valid_idx, 'j'], alpha=0.3, s=10)
    ax.axhline(80, color='red', linestyle=':', alpha=0.5)
    ax.axvline(80, color='red', linestyle=':', alpha=0.5)
    ax.set_xlabel('前1日J值')
    ax.set_ylabel('涨停日J值')
    ax.set_title('前1日J值 vs 涨停日J值')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'limit_up_indicators_chart.png', dpi=150, bbox_inches='tight')
    print("图表已保存: outputs/intraday_0945/limit_up_indicators_chart.png")


def main():
    df, failed = analyze_limit_up_indicators()
    if not df.empty:
        df = add_names_and_save(df)
        print_statistics(df)
        generate_charts(df)

    # 保存失败记录
    if failed:
        pd.DataFrame(failed, columns=['ts_code', 'trade_date', 'reason']).to_csv(
            OUTPUT_DIR / 'limit_up_indicators_failed.csv', index=False, encoding='utf-8-sig')


if __name__ == '__main__':
    main()
