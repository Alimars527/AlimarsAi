import sys
import json
import copy
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

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


def forward_return(store, code, trade_date, hold_days=1):
    df = store.load('daily', code)
    if df.empty:
        return None
    df = df.sort_values('trade_date').reset_index(drop=True)
    idx = df.index[df['trade_date'].astype(str) == str(trade_date)]
    if len(idx) == 0:
        return None
    i = int(idx[0])
    if i + hold_days >= len(df):
        return None
    try:
        buy = float(df.iloc[i]['close'])
        sell = float(df.iloc[i + hold_days]['close'])
        return round((sell - buy) / buy * 100, 4)
    except Exception:
        return None


if __name__ == '__main__':
    selector = CandidateSelector()
    scanner = FullMarketScanner()
    store = LocalDataStore(project_root / 'data')
    end_day = datetime(2026, 3, 21)
    rows = []

    idx_df = store.load('index_daily', '000001.SH')
    valid_days = set(idx_df['trade_date'].astype(str).tolist()) if not idx_df.empty else set()

    for i in range(10):
        day = end_day - timedelta(days=i)
        trade_date = day.strftime('%Y%m%d')
        if trade_date not in valid_days:
            continue
        hot_candidates = selector.select_from_hot_sectors([], trade_date, top_n=8, focus_industries=None)
        scan_candidates = scanner.scan(trade_date, top_n=12)
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

        for top_n in [3, 5]:
            with_returns = []
            without_returns = []
            for item in with_mf[:top_n]:
                r = forward_return(store, item['code'], trade_date, hold_days=1)
                if r is not None:
                    with_returns.append(r)
            for item in without_mf[:top_n]:
                r = forward_return(store, item['code'], trade_date, hold_days=1)
                if r is not None:
                    without_returns.append(r)
            rows.append({
                'trade_date': trade_date,
                'top_n': top_n,
                'with_mf_avg_return_1d': round(sum(with_returns) / len(with_returns), 4) if with_returns else None,
                'without_mf_avg_return_1d': round(sum(without_returns) / len(without_returns), 4) if without_returns else None,
                'with_count': len(with_returns),
                'without_count': len(without_returns),
            })

    df = pd.DataFrame(rows)
    summary = []
    if not df.empty:
        for top_n, g in df.groupby('top_n'):
            summary.append({
                'top_n': int(top_n),
                'with_mf_avg_return_1d': round(float(g['with_mf_avg_return_1d'].dropna().mean()), 4) if not g['with_mf_avg_return_1d'].dropna().empty else None,
                'without_mf_avg_return_1d': round(float(g['without_mf_avg_return_1d'].dropna().mean()), 4) if not g['without_mf_avg_return_1d'].dropna().empty else None,
            })
    print(json.dumps({'status': 'ok', 'summary': summary, 'rows': rows}, ensure_ascii=False, indent=2))
