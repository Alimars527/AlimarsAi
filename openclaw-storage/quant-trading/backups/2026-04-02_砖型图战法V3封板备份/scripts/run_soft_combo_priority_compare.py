import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.priority_ranker import rank_candidates_for_execution


def load_rows():
    path = project_root / 'outputs' / 'margin_industry_combo_validation_2026-03-22.txt'
    text = path.read_text(encoding='utf-8')
    data = eval(text, {'__builtins__': {}}, {'nan': float('nan')})
    return data['rows']


def build_candidates(rows, soft_combo=False):
    candidates = []
    for r in rows:
        score = 5
        if soft_combo:
            if r.get('hkhold_positive'):
                score += 1
            if r.get('margin_positive') and r.get('industry') == '元器件':
                score += 2
            elif r.get('margin_positive'):
                score += 0.5
        candidates.append({
            'code': r['ts_code'],
            'name': r['name'],
            'industry': r['industry'],
            'score': score,
            'pct_chg': 0,
            'trend_style': '稳定趋势主线',
            'execution_style': '',
            'mf_divergence': False,
            'mf_positive_5': True,
            'mf_positive_days_5_ok': True,
            'reason': '组合软融合验证',
            'hkhold_ratio': 1 if r.get('hkhold_positive') else 0,
            'hkhold_ratio_change': 1 if r.get('hkhold_positive') else 0,
            'hkhold_positive_5': 3 if r.get('hkhold_positive') else 0,
            'base_avg_return': r.get('avg_return'),
            'base_avg_exit_return': r.get('avg_exit_return'),
            'margin_positive': r.get('margin_positive'),
            'hkhold_positive': r.get('hkhold_positive'),
        })
    return candidates


if __name__ == '__main__':
    rows = load_rows()
    without_combo = rank_candidates_for_execution(build_candidates(rows, soft_combo=False))
    with_combo = rank_candidates_for_execution(build_candidates(rows, soft_combo=True))

    base_rank = {x['code']: i + 1 for i, x in enumerate(without_combo)}
    new_rank = {x['code']: i + 1 for i, x in enumerate(with_combo)}
    merged = []
    for x in with_combo:
        code = x['code']
        merged.append({
            'code': code,
            'name': x['name'],
            'industry': x['industry'],
            'rank_without_combo': base_rank[code],
            'rank_with_combo': new_rank[code],
            'rank_shift': base_rank[code] - new_rank[code],
            'priority_score': x['priority_score'],
            'base_avg_return': x.get('base_avg_return'),
            'base_avg_exit_return': x.get('base_avg_exit_return'),
            'hkhold_positive': x.get('hkhold_positive'),
            'margin_positive': x.get('margin_positive'),
        })
    df = pd.DataFrame(merged)
    print({
        'status': 'ok',
        'summary': {
            'total': int(len(df)),
            'improved_count': int((df['rank_shift'] > 0).sum()),
            'worsened_count': int((df['rank_shift'] < 0).sum()),
            'unchanged_count': int((df['rank_shift'] == 0).sum()),
        },
        'top_with_combo': df.sort_values('rank_with_combo').head(10).to_dict(orient='records'),
        'improved': df[df['rank_shift'] > 0].sort_values('rank_shift', ascending=False).to_dict(orient='records'),
        'worsened': df[df['rank_shift'] < 0].sort_values('rank_shift').to_dict(orient='records'),
    })
