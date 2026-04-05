import sys
from pathlib import Path
import copy
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.priority_ranker import rank_candidates_for_execution


def load_validation_rows():
    path = project_root / 'outputs' / 'hkhold_score_validation_2026-03-21.txt'
    text = path.read_text(encoding='utf-8')
    data = eval(text, {'__builtins__': {}}, {'nan': float('nan')})
    return data['high_score_group'] + data['low_score_group']


def make_candidates(rows, with_hkhold=True):
    candidates = []
    for r in rows:
        c = {
            'code': r['ts_code'],
            'name': r['name'],
            'industry': r['industry'],
            'score': 5,
            'pct_chg': 0,
            'trend_style': r['dominant_style'],
            'execution_style': '',
            'mf_divergence': False,
            'mf_positive_5': True,
            'mf_positive_days_5_ok': True,
            'reason': '验证样本',
            'base_avg_return': r.get('avg_return'),
            'base_avg_exit_return': r.get('avg_exit_return'),
        }
        if with_hkhold:
            c.update({
                'hkhold_ratio': r.get('hkhold_ratio', 0),
                'hkhold_ratio_change': r.get('hkhold_ratio_change', 0),
                'hkhold_positive_5': r.get('hkhold_positive_5', 0),
            })
        else:
            c.update({
                'hkhold_ratio': 0,
                'hkhold_ratio_change': 0,
                'hkhold_positive_5': 0,
            })
        candidates.append(c)
    return candidates


if __name__ == '__main__':
    rows = load_validation_rows()
    without_hk = rank_candidates_for_execution(make_candidates(rows, with_hkhold=False))
    with_hk = rank_candidates_for_execution(make_candidates(rows, with_hkhold=True))

    base_rank = {x['code']: i + 1 for i, x in enumerate(without_hk)}
    new_rank = {x['code']: i + 1 for i, x in enumerate(with_hk)}
    merged = []
    for x in with_hk:
        code = x['code']
        merged.append({
            'code': code,
            'name': x['name'],
            'industry': x['industry'],
            'rank_without_hkhold': base_rank[code],
            'rank_with_hkhold': new_rank[code],
            'rank_shift': base_rank[code] - new_rank[code],
            'priority_score_with_hkhold': x['priority_score'],
            'hkhold_flags': x.get('hkhold_flags', []),
            'base_avg_return': x.get('base_avg_return'),
            'base_avg_exit_return': x.get('base_avg_exit_return'),
        })
    df = pd.DataFrame(merged)
    improved = df[df['rank_shift'] > 0].sort_values('rank_shift', ascending=False)
    worsened = df[df['rank_shift'] < 0].sort_values('rank_shift')
    unchanged = df[df['rank_shift'] == 0]
    print({
        'status': 'ok',
        'summary': {
            'total': int(len(df)),
            'improved_count': int(len(improved)),
            'worsened_count': int(len(worsened)),
            'unchanged_count': int(len(unchanged)),
        },
        'improved': improved.to_dict(orient='records'),
        'worsened': worsened.to_dict(orient='records'),
        'top_with_hkhold': df.sort_values('rank_with_hkhold').head(10).to_dict(orient='records'),
    })
