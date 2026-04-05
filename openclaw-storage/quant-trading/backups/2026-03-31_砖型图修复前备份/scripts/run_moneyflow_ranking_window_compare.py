import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
import copy

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.candidate_selector import CandidateSelector
from quant.full_market_scan import FullMarketScanner
from quant.execution_filter import filter_for_next_day
from quant.priority_ranker import rank_candidates_for_execution
from quant.local_data_store import LocalDataStore


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
    selector = CandidateSelector()
    scanner = FullMarketScanner()
    store = LocalDataStore(project_root / 'data')
    end_day = datetime(2026, 3, 21)
    rows = []
    for i in range(10):
        day = end_day - timedelta(days=i)
        trade_date = day.strftime('%Y%m%d')
        try:
            # 只在本地已有该日指数/个股数据的情况下跑，避免无谓远端取数失败拖垮整个窗口
            idx = store.load('index_daily', '000001.SH')
            if idx.empty or trade_date not in set(idx['trade_date'].astype(str).tolist()):
                continue
            hot_candidates = selector.select_from_hot_sectors([], trade_date, top_n=8, focus_industries=None)
            scan_candidates = scanner.scan(trade_date, top_n=12)
        except Exception as e:
            rows.append({'trade_date': trade_date, 'error': str(e).splitlines()[0][:200]})
            continue
        merged = hot_candidates[:]
        existing = {c['code'] for c in merged}
        for c in scan_candidates:
            if c['code'] not in existing:
                merged.append(c)
        candidates = filter_for_next_day(merged[:12])
        if not candidates:
            continue
        with_mf = rank_candidates_for_execution(candidates)
        without_mf = rank_without_moneyflow(candidates)
        base_rank = {x['code']: idx + 1 for idx, x in enumerate(without_mf)}
        for idx, item in enumerate(with_mf, 1):
            rows.append({
                'trade_date': trade_date,
                'code': item.get('code'),
                'name': item.get('name'),
                'industry': item.get('industry'),
                'rank_with_mf': idx,
                'rank_without_mf': base_rank.get(item.get('code')),
                'rank_change': (base_rank.get(item.get('code')) or idx) - idx,
                'priority_score': item.get('priority_score'),
                'moneyflow_flags': item.get('moneyflow_flags', []),
                'mf_divergence': item.get('mf_divergence'),
                'mf_positive_5': item.get('mf_positive_5'),
                'mf_positive_days_5_ok': item.get('mf_positive_days_5_ok'),
            })
    print(json.dumps({'status': 'ok', 'rows': rows}, ensure_ascii=False, indent=2))
