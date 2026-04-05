import json
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT/'outputs'/'b2_frequency_20230101_20260325_state.jsonl'
OUT = PROJECT_ROOT/'outputs'/'b1b2_structure_v2_check_2026-03-26.json'

rows=[]
with SOURCE.open('r', encoding='utf-8') as f:
    for line in f:
        line=line.strip()
        if line:
            rows.append(json.loads(line))

df = pd.DataFrame(rows)
df['pct_chg']=pd.to_numeric(df['pct_chg'], errors='coerce')
df['b1_strength']=pd.to_numeric(df['b1_strength'], errors='coerce')
df['b2_strength']=pd.to_numeric(df['b2_strength'], errors='coerce')

# 结构V2：先把数值底座固定为当前正例共性，再继续排除砖型图
mask = (
    (df['hit_b2'] == True)
    & (df['hit_b1'] == True)
    & (df['hit_brick'] != True)
    & (df['b1_strength'] >= 5)
    & (df['b2_strength'] == 4)
    & (df['pct_chg'] >= 4.7)
    & (df['pct_chg'] <= 5.8)
)
sub = df[mask].copy()
sub['trade_date'] = sub['trade_date'].astype(str)
sub = sub.sort_values(['code','trade_date'])
sub['trade_date_dt'] = pd.to_datetime(sub['trade_date'])
keep=[]
last={}
for idx,row in sub.iterrows():
    code=row['code']; td=row['trade_date_dt']
    if code not in last or (td-last[code]).days > 10:
        keep.append(idx); last[code]=td
sub = sub.loc[keep].copy()

daily = sub.groupby('trade_date').agg(symbol_count=('code','nunique')).reset_index().sort_values('trade_date') if not sub.empty else pd.DataFrame(columns=['trade_date','symbol_count'])
if not daily.empty:
    daily['trade_date'] = pd.to_datetime(daily['trade_date'])
    gaps = daily['trade_date'].diff().dropna().dt.days
    freq = {
        'event_count': int(len(sub)),
        'signal_days': int(len(daily)),
        'avg_symbols_per_signal_day': float(daily['symbol_count'].mean()),
        'avg_gap_days': float(gaps.mean()) if not gaps.empty else None,
        'median_gap_days': float(gaps.median()) if not gaps.empty else None,
    }
else:
    freq = {'event_count':0,'signal_days':0,'avg_symbols_per_signal_day':None,'avg_gap_days':None,'median_gap_days':None}

rets=[]
for code, g in sub.groupby('code'):
    p = PROJECT_ROOT/f'data/daily/{code}.csv'
    if not p.exists():
        continue
    px = pd.read_csv(p)
    px['trade_date']=px['trade_date'].astype(str)
    px=px.sort_values('trade_date').reset_index(drop=True)
    idx_map={td:i for i,td in enumerate(px['trade_date'])}
    for _, r in g.iterrows():
        td = r['trade_date']
        if td not in idx_map: continue
        i = idx_map[td]
        if i+1 >= len(px): continue
        c0 = pd.to_numeric(px.loc[i,'close'], errors='coerce')
        c1 = pd.to_numeric(px.loc[i+1,'close'], errors='coerce')
        if pd.isna(c0) or pd.isna(c1) or c0 == 0: continue
        rets.append((c1/c0 - 1) * 100)
ret_s = pd.Series(rets, dtype='float64')
returns = {
    'sample_count': int(len(ret_s)),
    'avg_return': float(ret_s.mean()) if len(ret_s) else None,
    'median_return': float(ret_s.median()) if len(ret_s) else None,
    'win_rate': float((ret_s>0).mean()) if len(ret_s) else None,
}
res = {'name':'B1B2_STRUCTURE_V2_BASELINE','frequency':freq,'returns':returns}
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(res, ensure_ascii=False, indent=2))
