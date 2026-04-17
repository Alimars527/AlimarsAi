import pandas as pd
import tushare as ts
import sys, os

pro = ts.pro_api('be0e395aeb600a02110bcac4fca37a8d5b792afe8f13507040357d23')

# 1. 上证指数近10日
idx = pro.index_daily(ts_code='000001.SH', start_date='20260407', end_date='20260417')
idx = idx.sort_values('trade_date')
print('=== 上证指数近10日 ===')
print(idx[['trade_date','open','high','low','close','vol','pct_chg']].to_string(index=False))

# 2. 持仓个股近10日
for code in ['002378.SZ','600487.SH']:
    df = pro.daily(ts_code=code, start_date='20260407', end_date='20260417')
    df = df.sort_values('trade_date')
    basic = pro.daily_basic(ts_code=code, start_date='20260417', end_date='20260417')
    print(f'\n=== {code} 近10日 ===')
    print(df[['trade_date','open','high','low','close','vol','pct_chg']].to_string(index=False))
    if len(basic) > 0:
        b = basic.iloc[0]
        print(f'  总市值:{b.get("total_mv","N/A")}  流通市值:{b.get("circ_mv","N/A")}  PE:{b.get("pe_ttm","N/A")}  换手率:{b.get("turnover_rate","N/A")}')

# 3. 板块轮动 - 全市场按行业聚合
stock_basic = pro.stock_basic(exchange='', list_status='L', fields='ts_code,industry,name')
daily = pro.daily(trade_date='20260417')
merged = daily.merge(stock_basic, on='ts_code', how='left')
sector = merged.groupby('industry').agg(
    count=('ts_code', 'count'),
    avg_chg=('pct_chg', 'mean'),
    up_count=('pct_chg', lambda x: (x > 0).sum()),
    total_amount=('amount', 'sum')
).reset_index()
sector['win_rate'] = (sector['up_count'] / sector['count'] * 100).round(1)
sector = sector.sort_values('avg_chg', ascending=False)
print('\n=== 板块涨幅TOP15 ===')
print(sector.head(15).to_string(index=False))
print('\n=== 板块跌幅TOP10 ===')
print(sector.tail(10).to_string(index=False))

# 4. 持仓个股所属板块表现
for ind in ['通信','有色金属']:
    row = sector[sector['industry'] == ind]
    if len(row) > 0:
        print(f'\n{ind}板块: 涨幅均值={row.iloc[0]["avg_chg"]:.2f}%, 胜率={row.iloc[0]["win_rate"]:.1f}%, 个股数={row.iloc[0]["count"]}')
