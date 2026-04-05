import json, time
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = PROJECT_ROOT/'outputs'/'b1b2_resonance_grid_state.jsonl'
PROGRESS_PATH = PROJECT_ROOT/'outputs'/'b1b2_resonance_grid_progress.json'
OUT_PATH = PROJECT_ROOT/'outputs'/'b1b2_resonance_grid_results.json'
SOURCE_PATH = PROJECT_ROOT/'outputs'/'b2_frequency_20230101_20260325_state.jsonl'
RET_PATH = PROJECT_ROOT/'outputs'/'b2_b1_only_returns_summary_20230101_20260325.json'
PROGRESS_EVERY = 2

GRID = [
    {'name':'V2_A','b1_min':5,'b2_min':4,'b2_max':4,'pct_low':4.7,'pct_high':5.8,'exclude_brick':True,'gap_days':10},
    {'name':'V2_B','b1_min':5,'b2_min':4,'b2_max':4,'pct_low':4.8,'pct_high':5.5,'exclude_brick':True,'gap_days':10},
    {'name':'V2_C','b1_min':6,'b2_min':4,'b2_max':4,'pct_low':4.7,'pct_high':5.8,'exclude_brick':True,'gap_days':10},
    {'name':'V2_D','b1_min':5,'b2_min':3,'b2_max':4,'pct_low':4.7,'pct_high':5.8,'exclude_brick':True,'gap_days':10},
    {'name':'V2_E','b1_min':5,'b2_min':4,'b2_max':4,'pct_low':4.7,'pct_high':5.8,'exclude_brick':True,'gap_days':15},
]


def write_progress(processed, total, status='running', last=None):
    payload = {'status': status, 'processed': processed, 'total': total, 'progress_pct': round(processed/total,4) if total else 0, 'last': last}
    PROGRESS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def load_rows(path):
    rows=[]
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if line:
                rows.append(json.loads(line))
    return pd.DataFrame(rows)


def load_state():
    if not STATE_PATH.exists():
        return 0, []
    rows=[]; idx=0
    with STATE_PATH.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if line:
                obj=json.loads(line); rows.append(obj); idx=max(idx, int(obj.get('_grid_idx',0)))
    return idx, rows


def append_state(obj):
    with STATE_PATH.open('a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False)+'\n')


def dedup_wave(sub, gap_days):
    if sub.empty:
        return sub
    sub=sub.sort_values(['code','trade_date']).copy()
    sub['trade_date_dt']=pd.to_datetime(sub['trade_date'])
    keep=[]; last={}
    for idx,row in sub.iterrows():
        code=row['code']; td=row['trade_date_dt']
        if code not in last or (td-last[code]).days > gap_days:
            keep.append(idx); last[code]=td
    return sub.loc[keep].copy()


def calc_returns(sub):
    results=[]
    for code, g in sub.groupby('code'):
        p = PROJECT_ROOT/f'data/daily/{code}.csv'
        if not p.exists():
            continue
        px = pd.read_csv(p)
        px['trade_date']=px['trade_date'].astype(str)
        px=px.sort_values('trade_date').reset_index(drop=True)
        idx_map = {td:i for i,td in enumerate(px['trade_date'])}
        for _, r in g.iterrows():
            td=r['trade_date']
            if td not in idx_map: continue
            i=idx_map[td]
            if i+1>=len(px): continue
            c0=pd.to_numeric(px.loc[i,'close'], errors='coerce')
            c1=pd.to_numeric(px.loc[i+1,'close'], errors='coerce')
            if pd.isna(c0) or pd.isna(c1) or c0==0: continue
            ret=(c1/c0-1)*100
            results.append(ret)
    if not results:
        return {'sample_count':0}
    s=pd.Series(results)
    return {
        'sample_count': int(len(s)),
        'avg_return': float(s.mean()),
        'median_return': float(s.median()),
        'win_rate': float((s>0).mean()),
    }

if __name__ == '__main__':
    df = load_rows(SOURCE_PATH)
    df['trade_date']=df['trade_date'].astype(str)
    df['pct_chg']=pd.to_numeric(df['pct_chg'], errors='coerce')
    df['b1_strength']=pd.to_numeric(df['b1_strength'], errors='coerce')
    df['b2_strength']=pd.to_numeric(df['b2_strength'], errors='coerce')
    start_idx, rows = load_state()
    write_progress(start_idx, len(GRID), last=None)
    for i, cfg in enumerate(GRID[start_idx:], start=start_idx+1):
        mask = (df['hit_b2']==True) & (df['hit_b1']==True) & (df['b1_strength']>=cfg['b1_min']) & (df['b2_strength']>=cfg['b2_min']) & (df['b2_strength']<=cfg['b2_max']) & (df['pct_chg']>=cfg['pct_low']) & (df['pct_chg']<=cfg['pct_high'])
        if cfg['exclude_brick']:
            mask = mask & (df['hit_brick']!=True)
        sub = df[mask].copy()
        dedup = dedup_wave(sub, cfg['gap_days'])
        daily = dedup.groupby('trade_date').agg(symbol_count=('code','nunique')).reset_index().sort_values('trade_date') if not dedup.empty else pd.DataFrame(columns=['trade_date','symbol_count'])
        if not daily.empty:
            daily['trade_date']=pd.to_datetime(daily['trade_date'])
            gaps = daily['trade_date'].diff().dropna().dt.days
            freq = {
                'event_count': int(len(dedup)),
                'signal_days': int(len(daily)),
                'avg_symbols_per_signal_day': float(daily['symbol_count'].mean()),
                'avg_gap_days': float(gaps.mean()) if not gaps.empty else None,
                'median_gap_days': float(gaps.median()) if not gaps.empty else None,
            }
        else:
            freq = {'event_count':0,'signal_days':0,'avg_symbols_per_signal_day':None,'avg_gap_days':None,'median_gap_days':None}
        ret = calc_returns(dedup)
        out = {'_grid_idx': i, 'name': cfg['name'], 'config': cfg, 'frequency': freq, 'returns': ret}
        append_state(out)
        rows.append(out)
        if i % PROGRESS_EVERY == 0 or i == len(GRID):
            write_progress(i, len(GRID), last=cfg['name'])
        time.sleep(0.05)
    result = {'results': rows}
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    write_progress(len(GRID), len(GRID), status='done', last=None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
