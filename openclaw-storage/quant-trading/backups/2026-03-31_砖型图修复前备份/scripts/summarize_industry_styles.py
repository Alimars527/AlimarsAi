import json
from pathlib import Path
import pandas as pd
import sys

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.industry_style_map import classify_industry_style

stock_basic = project_root / 'data' / 'meta' / 'stock_basic.csv'
out_path = project_root / 'outputs' / 'industry_style_summary_2026-03-23.json'

if not stock_basic.exists():
    raise SystemExit('missing stock_basic.csv')

df = pd.read_csv(stock_basic, dtype=str)
if 'industry' not in df.columns:
    raise SystemExit('missing industry column')

df['style_group'] = df['industry'].fillna('').apply(classify_industry_style)
summary = df.groupby('style_group').agg(count=('ts_code', 'count')).reset_index().sort_values('count', ascending=False)
unknown = df[df['style_group'] == 'unclassified']['industry'].fillna('').value_counts().head(50).to_dict()

out = {
    'status': 'ok',
    'style_counts': summary.to_dict(orient='records'),
    'top_unclassified_industries': unknown,
}

out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(out)
