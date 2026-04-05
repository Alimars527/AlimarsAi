import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.priority_ranker import rank_candidates_for_execution
from quant.hkhold_policy import hkhold_policy_for_industry


def build_sample_candidates():
    path = project_root / 'outputs' / 'hkhold_score_validation_2026-03-21.txt'
    text = path.read_text(encoding='utf-8')
    data = eval(text, {'__builtins__': {}}, {'nan': float('nan')})
    rows = data['high_score_group'] + data['low_score_group']
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
            'hkhold_ratio': r.get('hkhold_ratio', 0),
            'hkhold_ratio_change': r.get('hkhold_ratio_change', 0),
            'hkhold_positive_5': r.get('hkhold_positive_5', 0),
            'base_avg_return': r.get('avg_return'),
            'base_avg_exit_return': r.get('avg_exit_return'),
        }
        candidates.append(c)
    return candidates


if __name__ == '__main__':
    candidates = build_sample_candidates()
    ranked = rank_candidates_for_execution(candidates)
    out = []
    for x in ranked:
        policy = hkhold_policy_for_industry(x.get('industry', ''), x.get('hkhold_ratio', 0), x.get('hkhold_ratio_change', 0), x.get('hkhold_positive_5', 0))
        out.append({
            'code': x.get('code'),
            'name': x.get('name'),
            'industry': x.get('industry'),
            'priority_score': x.get('priority_score'),
            'hkhold_score': policy.get('hkhold_score'),
            'hkhold_flags': x.get('hkhold_flags', []),
            'base_avg_return': x.get('base_avg_return'),
            'base_avg_exit_return': x.get('base_avg_exit_return'),
        })
    df = pd.DataFrame(out)
    print({
        'status': 'ok',
        'top_ranked': df.head(10).to_dict(orient='records'),
        'bottom_ranked': df.tail(10).to_dict(orient='records'),
    })
