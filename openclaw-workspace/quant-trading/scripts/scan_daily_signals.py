#!/usr/bin/env python3
"""每日复盘扫描脚本 - 砖型图信号 + B1信号"""
import tushare as ts
import pandas as pd
import numpy as np
import sys

pro = ts.pro_api('be0e395aeb600a02110bcac4fca37a8d5b792afe8f13507040357d23')
TRADE_DATE = sys.argv[1] if len(sys.argv) > 1 else '20260416'

EXCLUDED = {'航空','电气设备','旅游服务','黄金','全国地产','轻工机械','农药化肥','石油贸易','矿物制品','专用机械','化纤','焦炭加工','其他商业','装修装饰'}

# ===== 1. Batch fetch last 15 trading days for ALL stocks =====
print(f"拉取全市场数据: {TRADE_DATE} 前15个交易日...")
# Fetch in chunks of dates to avoid API limits
all_data = []
for start in ['20260327', '20260401', '20260407', '20260410', '20260414']:
    try:
        chunk = pro.daily(start_date=start, end_date=TRADE_DATE)
        if chunk is not None and len(chunk) > 0:
            all_data.append(chunk)
            print(f"  {start}~{TRADE_DATE}: {len(chunk)} 条")
    except Exception as e:
        print(f"  {start}: 错误 {e}")

if not all_data:
    print("无数据"); sys.exit(1)

df = pd.concat(all_data, ignore_index=True).drop_duplicates(subset=['ts_code','trade_date'])
print(f"合并后: {len(df)} 条, {df['ts_code'].nunique()} 只股票")

# ===== 2. Stock basic + industry =====
basic = pro.stock_basic(fields='ts_code,industry,name')
name_map = dict(zip(basic['ts_code'], basic['name']))
industry_map = dict(zip(basic['ts_code'], basic['industry']))

df = df.merge(basic[['ts_code','industry']], on='ts_code', how='left')

# Filter: non-excluded, non-ST, non-科创板/北交所
df = df[
    ~df['industry'].isin(EXCLUDED) &
    df['ts_code'].str.match(r'^[063]\d{5}\.(SZ|SH)$', na=False) &
    ~df['ts_code'].str.startswith('688', na=False)
]

print(f"过滤后: {len(df)} 条, {df['ts_code'].nunique()} 只股票")

# ===== 3. Sector rotation (from ALL stocks) =====
all_day = pro.daily(trade_date=TRADE_DATE)
all_day = all_day.merge(basic[['ts_code','industry']], on='ts_code', how='left')
sector_avg = all_day.groupby('industry')['pct_chg'].mean().sort_values(ascending=False)
top5_sectors = set(sector_avg.head(5).index.tolist())
print(f"\n轮动Top5: {', '.join(sector_avg.head(5).index.tolist())}")
print(f"轮动Bottom5: {', '.join(sector_avg.tail(5).index.tolist())}")

# ===== 4. Brick chart signal scan =====
print(f"\n{'='*60}")
print("砖型图信号扫描")
print(f"{'='*60}")

df_sorted = df.sort_values(['ts_code','trade_date'])

signals = []
for code, group in df_sorted.groupby('ts_code'):
    group = group.sort_values('trade_date').reset_index(drop=True)
    if len(group) < 6:
        continue
    
    group['ma5'] = group['close'].rolling(5, min_periods=5).mean()
    group['ma10'] = group['close'].rolling(10, min_periods=10).mean()
    
    # Only check last row (today)
    today = group.iloc[-1]
    if today['trade_date'] != TRADE_DATE:
        continue
    
    yesterday = group.iloc[-2]
    
    # XG=1: yesterday green (close<open), today red (close>open)
    if not (today['close'] > today['open'] and yesterday['close'] < yesterday['open']):
        continue
    
    # Quality 1: today not entirely below white line
    if pd.isna(today['ma5']) or today['high'] < today['ma5']:
        continue
    
    # Quality 2-3: prior 4 days all green with decreasing body
    if len(group) < 6:
        continue
    prior_4 = group.iloc[-5:-1]
    if not all(prior_4['close'].values < prior_4['open'].values):
        continue
    bodies = prior_4['open'].values - prior_4['close'].values
    if not all(bodies[i] >= bodies[i+1] for i in range(len(bodies)-1)):
        continue
    
    # Quality 4: today red body >= yesterday green body
    today_body = today['close'] - today['open']
    yesterday_body = yesterday['open'] - yesterday['close']
    if today_body < yesterday_body:
        continue
    
    # Quality 5: white above yellow
    if pd.isna(today['ma5']) or pd.isna(today['ma10']):
        continue
    if today['ma5'] < today['ma10']:
        continue
    
    name = name_map.get(code, 'N/A')
    industry = industry_map.get(code, 'N/A')
    in_top5 = industry in top5_sectors
    
    signals.append({
        'code': code, 'name': name, 'industry': industry,
        'close': today['close'], 'pct_chg': today['pct_chg'],
        'vol': today['vol'], 'in_top5': in_top5,
        'today_body': today_body, 'yesterday_body': yesterday_body,
    })

print(f"砖型图优质信号: {len(signals)} 只")
if signals:
    sig_df = pd.DataFrame(signals).sort_values('pct_chg', ascending=False)
    
    top5_s = sig_df[sig_df['in_top5']]
    other_s = sig_df[~sig_df['in_top5']]
    
    if len(top5_s) > 0:
        print(f"\n--- 轮动Top5行业内 ({len(top5_s)}只) ★推荐---")
        for _, r in top5_s.iterrows():
            ratio = r['today_body'] / r['yesterday_body']
            print(f"  {r['code']} {r['name']:6s} | {r['industry']:8s} | {r['close']:>7.2f} | {r['pct_chg']:>+6.2f}% | 砖比:{ratio:.2f}")
    
    if len(other_s) > 0:
        print(f"\n--- 其他行业 ({len(other_s)}只) ---")
        for _, r in other_s.head(15).iterrows():
            ratio = r['today_body'] / r['yesterday_body']
            print(f"  {r['code']} {r['name']:6s} | {r['industry']:8s} | {r['close']:>7.2f} | {r['pct_chg']:>+6.2f}% | 砖比:{ratio:.2f}")

# ===== 5. Basic XG=1 (no quality filter) for reference =====
print(f"\n{'='*60}")
print("基础XG=1信号(绿转红,无质量过滤)")
print(f"{'='*60}")

xg1_list = []
for code, group in df_sorted.groupby('ts_code'):
    group = group.sort_values('trade_date').reset_index(drop=True)
    if len(group) < 2:
        continue
    today = group.iloc[-1]
    if today['trade_date'] != TRADE_DATE:
        continue
    yesterday = group.iloc[-2]
    if today['close'] > today['open'] and yesterday['close'] < yesterday['open']:
        xg1_list.append({
            'code': code, 'name': name_map.get(code,'?'),
            'industry': industry_map.get(code,'?'),
            'close': today['close'], 'pct_chg': today['pct_chg'],
            'in_top5': industry_map.get(code,'?') in top5_sectors
        })

xg1_df = pd.DataFrame(xg1_list).sort_values('pct_chg', ascending=False)
print(f"全市场XG=1: {len(xg1_df)} 只")
xg1_top5 = xg1_df[xg1_df['in_top5']]
print(f"轮动Top5行业内XG=1: {len(xg1_top5)} 只")
if len(xg1_top5) > 0:
    for _, r in xg1_top5.head(10).iterrows():
        print(f"  {r['code']} {r['name']:6s} | {r['industry']:8s} | {r['close']:>7.2f} | {r['pct_chg']:>+6.2f}%")

# ===== 6. Holdings P&L =====
print(f"\n{'='*60}")
print("持仓盈亏")
print(f"{'='*60}")

holdings = [
    ('002756.SZ', '永兴材料', 71.77, 100),
    ('002709.SZ', '天赐材料', 46.39, 100),
    ('159545.SZ', '恒生红利ETF', 1.429, 35000),
    ('603127.SH', '昭衍新药', 38.025, 200),
    ('600549.SH', '厦门钨业', 60.596, 200),
    ('603685.SH', '晨丰科技', 30.695, 200),
]

total_inv = 0; total_val = 0
for code, name, cost, qty in holdings:
    row = all_day[all_day['ts_code'] == code]
    if len(row) > 0:
        close = row.iloc[0]['close']
        pct = row.iloc[0]['pct_chg']
        inv = cost * qty; val = close * qty
        pnl_pct = (close - cost) / cost * 100
        pnl_yuan = val - inv
        total_inv += inv; total_val += val
        print(f"  {name:8s}({code}) | 成本:{cost:.3f} 收:{close:.2f} | {pnl_pct:+.2f}% ({pnl_yuan:+,.0f}元) | 今日:{pct:+.2f}%")
    else:
        print(f"  {name:8s}({code}) | 无数据")
        total_inv += cost * qty; total_val += cost * qty

total_pnl = total_val - total_inv
total_pct = total_pnl / total_inv * 100 if total_inv > 0 else 0
print(f"\n  总投入:{total_inv:,.0f} | 总市值:{total_val:,.0f} | 盈亏:{total_pnl:+,.0f}元 ({total_pct:+.2f}%)")

print("\n扫描完成!")
