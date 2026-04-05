import sys
import json
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.batch_backtest import BatchBacktester
from quant.trend_tier_map import normalize_trend_tier
from quant.tactic_router import route_tactic

OUT = project_root / 'outputs' / 'tactic_group_backtest_2026-03-23.json'


def dominant_style_from_counts(style_counts):
    high = style_counts.get('高弹性主线', 0)
    stable = style_counts.get('稳定趋势主线', 0)
    edge = style_counts.get('边缘趋势', 0)
    total = high + stable + edge
    if total <= 0:
        return '边缘趋势'
    high_ratio = high / total
    stable_ratio = stable / total
    if high_ratio >= 0.22:
        return '高弹性主线'
    if stable_ratio >= 0.20:
        return '稳定趋势主线'
    return '边缘趋势'


if __name__ == '__main__':
    runner = BatchBacktester(project_root)
    universe = runner.filter_universe(runner.load_universe())
    rows = []
    total = len(universe)
    for idx, (_, r) in enumerate(universe.iterrows(), start=1):
        code = r['ts_code']
        name = r.get('name', '')
        industry = r.get('industry', '')
        result = runner.backtester.run_single_code(code, strategy_name='主线趋势', hold_days=1, industry=industry)
        if result.get('status') != 'ok':
            continue
        style_counts = result.get('style_counts', {})
        dominant_style = dominant_style_from_counts(style_counts)
        trend_tier = normalize_trend_tier(dominant_style)
        metric = result.get('metrics', {})
        exit_metrics = result.get('exit_metrics', {})
        item = {
            'code': code,
            'name': name,
            'industry': industry,
            'trend_tier': trend_tier,
            'strategy_tag': '主线趋势' if trend_tier in ['主线趋势-优先', '主线趋势-谨慎'] else '观察',
            'execution_style': '主线趋势，可重点观察' if trend_tier == '主线趋势-优先' else '可做埋伏观察',
            'reason': '',
            'avg_return': metric.get('avg_return'),
            'win_rate': metric.get('win_rate'),
            'exit_avg_return': exit_metrics.get('avg_return'),
            'exit_win_rate': exit_metrics.get('win_rate'),
            'signal_count': result.get('signal_count', 0),
        }
        item = route_tactic(item)
        rows.append(item)
        if idx % 500 == 0:
            print(f'progress {idx}/{total} rows={len(rows)}')

    df = pd.DataFrame(rows)
    for col in ['avg_return', 'win_rate', 'exit_avg_return', 'exit_win_rate']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    by_tactic = df.groupby(['tactic_family', 'tactic_signal']).agg(
        sample_count=('code', 'count'),
        avg_return=('avg_return', 'mean'),
        avg_win_rate=('win_rate', 'mean'),
        avg_exit_return=('exit_avg_return', 'mean'),
        avg_exit_win_rate=('exit_win_rate', 'mean'),
    ).reset_index().sort_values(['avg_return', 'avg_win_rate'], ascending=[False, False])
    out = {
        'status': 'ok',
        'universe_count': int(total),
        'result_count': int(len(df)),
        'by_tactic': by_tactic.to_dict(orient='records'),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(out)
