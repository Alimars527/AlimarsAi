"""持仓个股技术分析 + 候选票扫描"""
import pandas as pd
import tushare as ts
import numpy as np

pro = ts.pro_api('be0e395aeb600a02110bcac4fca37a8d5b792afe8f13507040357d23')

def analyze_stock(code, name, cost=None, days=30):
    """分析个股技术面"""
    df = pro.daily(ts_code=code, start_date='20260301', end_date='20260417')
    df = df.sort_values('trade_date').reset_index(drop=True)
    
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    vol = df['vol'].values
    
    # 均线
    ma5 = pd.Series(close).rolling(5).mean().values
    ma10 = pd.Series(close).rolling(10).mean().values
    ma20 = pd.Series(close).rolling(20).mean().values
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    print(f"\n{'='*60}")
    print(f"{name}({code}) 技术分析")
    print(f"{'='*60}")
    print(f"收盘:{last['close']:.2f}  涨跌:{last['pct_chg']:.2f}%")
    print(f"MA5:{ma5[-1]:.2f}  MA10:{ma10[-1]:.2f}  MA20:{ma20[-1]:.2f}")
    if cost:
        pnl = (last['close'] - cost) / cost * 100
        print(f"成本:{cost:.3f}  浮盈亏:{pnl:+.2f}%")
    
    # 近5日K线形态
    print(f"\n近5日K线:")
    for i in range(-5, 0):
        r = df.iloc[i]
        body = r['close'] - r['open']
        color = "红" if body > 0 else "绿"
        upper_shadow = r['high'] - max(r['open'], r['close'])
        lower_shadow = min(r['open'], r['close']) - r['low']
        print(f"  {r['trade_date']} {color} 开:{r['open']:.2f} 高:{r['high']:.2f} 低:{r['low']:.2f} 收:{r['close']:.2f} 量:{r['vol']:.0f} 涨跌:{r['pct_chg']:.2f}%")
    
    # 成交量趋势
    vol5 = vol[-5:].mean()
    vol10 = vol[-10:].mean()
    vol_ratio = vol5 / vol10 if vol10 > 0 else 0
    print(f"\n量能: 5日均量:{vol5:.0f}  10日均量:{vol10:.0f}  量比:{vol_ratio:.2f}")
    
    # 支撑压力位
    recent_high = high[-20:].max()
    recent_low = low[-20:].min()
    print(f"近20日高点:{recent_high:.2f}  低点:{recent_low:.2f}")
    
    # 砖型图判断（简化版：看3日趋势）
    if close[-1] > close[-2] > close[-3]:
        print("砖型图趋势: 连续红砖(3日连涨)")
    elif close[-1] < close[-2]:
        print("砖型图趋势: 出绿砖")
    else:
        print("砖型图趋势: 震荡")
    
    return {
        'close': last['close'], 'pct_chg': last['pct_chg'],
        'ma5': ma5[-1], 'ma10': ma10[-1], 'ma20': ma20[-1],
        'vol_ratio': vol_ratio, 'recent_high': recent_high, 'recent_low': recent_low
    }

# === 持仓分析 ===
print("╔══════════════════════════════════════╗")
print("║        持仓个股技术分析               ║")
print("╚══════════════════════════════════════╝")

analyze_stock('002378.SZ', '章源钨业', cost=32.114)
analyze_stock('600487.SH', '亨通光电', cost=53.336)

# === 候选票扫描 ===
print(f"\n{'='*60}")
print("候选票扫描（全市场）")
print(f"{'='*60}")

# 全市场数据
daily = pro.daily(trade_date='20260417')
daily_basic = pro.daily_basic(trade_date='20260417')
stock_basic = pro.stock_basic(exchange='', list_status='L', fields='ts_code,industry,name')

merged = daily.merge(daily_basic[['ts_code','total_mv','circ_mv','turnover_rate','pe_ttm']], on='ts_code', how='left')
merged = merged.merge(stock_basic, on='ts_code', how='left')

# 过滤：排除ST、科创板、北交所、停牌
merged = merged[~merged['name'].str.contains('ST|\\*ST', na=False)]
merged = merged[~merged['ts_code'].str.startswith('688')]
merged = merged[~merged['ts_code'].str.startswith('8')]
merged = merged[~merged['ts_code'].str.startswith('4')]
merged = merged[merged['pct_chg'].notna()]

# 砖型图+板块筛选：放量上涨、板块强度
# 筛选条件：涨幅>3%、换手>3%、成交额>5亿、非ST/科创/北交
candidates = merged[
    (merged['pct_chg'] > 3) & 
    (merged['turnover_rate'] > 3) & 
    (merged['amount'] > 50000) &  # 5千万（千元单位=5亿）
    (merged['total_mv'] > 500000) &  # 总市值>50亿
    (merged['total_mv'] < 5000000)  # 总市值<500亿
].copy()

# 按涨幅排序
candidates = candidates.sort_values('pct_chg', ascending=False)

# 板块过滤：T0/T1/T2优先
priority_sectors = ['半导体','通信设备','元器件','专用机械','小金属','矿物制品',
                    '铜','铅锌','电器仪表','塑料','橡胶','机床制造']
candidates['priority'] = candidates['industry'].apply(lambda x: 1 if x in priority_sectors else 0)
candidates = candidates.sort_values(['priority','pct_chg'], ascending=[False, False])

print(f"\n筛选结果: {len(candidates)} 只候选")
print(f"\n优先板块候选（前20）:")
print(candidates[['ts_code','name','industry','close','pct_chg','turnover_rate','amount']].head(20).to_string(index=False))

# 进一步：检查候选票近5日形态（砖型图红砖启动）
print(f"\n{'='*60}")
print("候选票近5日形态检查")
print(f"{'='*60}")
top_codes = candidates.head(15)['ts_code'].tolist()
for code in top_codes:
    df = pro.daily(ts_code=code, start_date='20260410', end_date='20260417')
    if len(df) < 3:
        continue
    df = df.sort_values('trade_date')
    name = candidates[candidates['ts_code']==code]['name'].values[0]
    ind = candidates[candidates['ts_code']==code]['industry'].values[0]
    
    closes = df['close'].values
    vols = df['vol'].values
    
    # 简化砖型图判断
    red_days = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i-1])
    vol_trend = "放量" if vols[-1] > vols[:-1].mean() else "缩量"
    
    # 看是否有回调后启动的形态
    if len(closes) >= 3:
        pattern = ""
        if closes[-1] > closes[-2] and closes[-2] < closes[-3]:
            pattern = "回调反弹"
        elif closes[-1] > closes[-2] > closes[-3]:
            pattern = "连涨"
        elif closes[-1] > closes[-2]:
            pattern = "转强"
        else:
            pattern = "整理"
    else:
        pattern = "N/A"
    
    print(f"  {code} {name}({ind}): {red_days}日红 {vol_trend} 形态:{pattern} 涨:{df.iloc[-1]['pct_chg']:.2f}%")
