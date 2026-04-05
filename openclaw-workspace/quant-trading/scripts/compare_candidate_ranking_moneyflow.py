import sys
from pathlib import Path
import copy

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.priority_ranker import rank_candidates_for_execution
import json


def rank_without_moneyflow(candidates):
    stripped = []
    for c in candidates:
        x = copy.deepcopy(c)
        x['mf_divergence'] = False
        x['mf_positive_5'] = False
        x['mf_positive_days_5_ok'] = False
        stripped.append(x)
    return rank_candidates_for_execution(stripped)


if __name__ == '__main__':
    p = project_root / 'outputs' / 'latest_summary.json'
    data = json.loads(p.read_text(encoding='utf-8'))
    candidates = data.get('candidates', [])
    with_mf = rank_candidates_for_execution(candidates)
    without_mf = rank_without_moneyflow(candidates)
    base_map = {x['code']: i + 1 for i, x in enumerate(without_mf)}
    rows = []
    for i, item in enumerate(with_mf, 1):
        rows.append({
            'code': item.get('code'),
            'name': item.get('name'),
            'industry': item.get('industry'),
            'rank_with_mf': i,
            'rank_without_mf': base_map.get(item.get('code')),
            'priority_score': item.get('priority_score'),
            'moneyflow_flags': item.get('moneyflow_flags', []),
            'mf_divergence': item.get('mf_divergence'),
            'mf_positive_5': item.get('mf_positive_5'),
            'mf_positive_days_5_ok': item.get('mf_positive_days_5_ok'),
        })
    print({'status': 'ok', 'rows': rows})
