import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.priority_ranker import rank_candidates_for_execution
from quant.margin_policy import margin_policy_for_industry
from quant.hkhold_policy import hkhold_policy_for_industry


def load_rows():
    path = project_root / 'outputs' / 'margin_industry_combo_validation_2026-03-22.txt'
    text = path.read_text(encoding='utf-8')
    data = eval(text, {'__builtins__': {}}, {'nan': float('nan')})
    return data['rows']


def build_candidates(rows, with_margin=True):
    candidates = []
    for r in rows:
        c = {
            'code': r['ts_code'],
            'name': r['name'],
            'industry': r['industry'],
            'score': 5,
            'pct_chg': 0,
            'trend_style': '稳定趋势主线',
            'execution_style': '',
            'mf_divergence': False,
            'mf_positive_5': True,
            'mf_positive_days_5_ok': True,
            'reason': '验证样本',
            'hkhold_ratio': 1 if r.get('hkhold_positive') else 0,
            'hkhold_ratio_change': 1 if r.get('hkhold_positive') else 0,
            'hkhold_positive_5': 3 if r.get('hkhold_positive') else 0,
            'base_avg_return': r.get('avg_return'),
            'base_avg_exit_return': r.get('avg_exit_return'),
        }
        if with_margin:
            c.update({
                'margin_net_buy_5': 1 if r.get('margin_positive') else 0,
                'margin_positive_days_5': 3 if r.get('margin_positive') else 0,
                'margin_rzye_change_5': 1 if r.get('margin_positive') else 0,
            })
        else:
            c.update({
                'margin_net_buy_5': 0,
                'margin_positive_days_5': 0,
                'margin_rzye_change_5': 0,
            })
        candidates.append(c)
    return candidates


def rank_with_margin_boost(candidates):
    ranked = rank_candidates_for_execution(candidates)
    for item in ranked:
        policy = margin_policy_for_industry(
            item.get('industry', ''),
            item.get('margin_net_buy_5', 0),
            item.get('margin_positive_days_5', 0),
            item.get('margin_rzye_change_5', 0),
        )
        if item.get('industry') == '元器件' and policy.get('margin_positive'):
            item['priority_score'] += 3
            item['margin_flags'] = [policy.get('margin_reason') or '融资正向']
        elif policy.get('margin_positive'):
            item['priority_score'] += 1
            item['margin_flags'] = [policy.get('margin_reason') or '融资正向']
        else:
            item['margin_flags'] = []
    ranked.sort(key=lambda x: (x['priority_score'], x.get('pct_chg', 0)), reverse=True)
    return ranked


if __name__ == '__main__':
    rows = load_rows()
    without_margin = rank_with_margin_boost(build_candidates(rows, with_margin=False))
    with_margin = rank_with_margin_boost(build_candidates(rows, with_margin=True))

    base_rank = {x['code']: i + 1 for i, x in enumerate(without_margin)}
    new_rank = {x['code']: i + 1 for i, x in enumerate(with_margin)}
    merged = []
    for x in with_margin:
        code = x['code']
        merged.append({
            'code': code,
            'name': x['name'],
            'industry': x['industry'],
            'rank_without_margin': base_rank[code],
            'rank_with_margin': new_rank[code],
            'rank_shift': base_rank[code] - new_rank[code],
            'priority_score': x['priority_score'],
            'margin_flags': x.get('margin_flags', []),
            'base_avg_return': x.get('base_avg_return'),
            'base_avg_exit_return': x.get('base_avg_exit_return'),
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
        'improved': df[df['rank_shift'] > 0].sort_values('rank_shift', ascending=False).to_dict(orient='records'),
        'top_with_margin': df.sort_values('rank_with_margin').head(10).to_dict(orient='records'),
    })
