import json
from pathlib import Path
import pandas as pd

ROOT = Path('/Users/alimars/.openclaw/workspace/quant-trading')
SRC = ROOT / 'outputs' / 'all_industries_backtest_latest.json'
DST = ROOT / 'outputs' / 'all_industries_backtest_cleaned.json'
FOCUS = ROOT / 'outputs' / 'all_industries_focus_sectors.json'

FOCUS_KEYWORDS = ['白酒', '酒', '石油', '光伏', '新能源', '电力', '医药', '半导体', '元器件', '电气设备', '软件服务']

with SRC.open('r', encoding='utf-8') as f:
    data = json.load(f)

rows = data.get('top_industries', []) + data.get('bottom_industries', [])
df = pd.DataFrame(rows).drop_duplicates(subset=['industry']) if rows else pd.DataFrame()

if df.empty:
    out = {'status': 'empty'}
    DST.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    FOCUS.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(out)
    raise SystemExit(0)

for col in ['avg_return', 'avg_win_rate', 'avg_exit_return', 'avg_exit_win_rate']:
    df[col] = pd.to_numeric(df[col], errors='coerce')

clean_df = df.dropna(subset=['avg_return', 'avg_win_rate', 'avg_exit_return', 'avg_exit_win_rate']).copy()
clean_df = clean_df.sort_values(['avg_return', 'avg_win_rate'], ascending=[False, False]).reset_index(drop=True)

focus_df = clean_df[clean_df['industry'].astype(str).apply(lambda x: any(k in x for k in FOCUS_KEYWORDS))].copy()

out = {
    'status': 'ok',
    'clean_industry_count': int(len(clean_df)),
    'top_industries': clean_df.head(30).to_dict(orient='records'),
    'bottom_industries': clean_df.tail(30).sort_values(['avg_return', 'avg_win_rate'], ascending=[True, True]).to_dict(orient='records'),
}
focus_out = {
    'status': 'ok',
    'focus_industry_count': int(len(focus_df)),
    'focus_industries': focus_df.to_dict(orient='records'),
}

DST.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
FOCUS.write_text(json.dumps(focus_out, ensure_ascii=False, indent=2), encoding='utf-8')
print({'clean_industry_count': len(clean_df), 'focus_industry_count': len(focus_df)})
