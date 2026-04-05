import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.batch_backtest import BatchBacktester
from quant.trend_tier_map import normalize_trend_tier


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
    universe = runner.filter_universe(runner.load_universe()).head(120)
    rows = []
    for _, r in universe.iterrows():
        code = r['ts_code']
        name = r.get('name', '')
        industry = r.get('industry', '')
        result = runner.backtester.run_single_code(code, strategy_name='主线趋势', hold_days=1, industry=industry)
        if result.get('status') != 'ok':
            continue
        metric = result.get('metrics', {})
        exit_metrics = result.get('exit_metrics', {})
        style_counts = result.get('style_counts', {})
        dominant_style = dominant_style_from_counts(style_counts)
        trend_tier = normalize_trend_tier(dominant_style)
        rows.append({
            'ts_code': code,
            'name': name,
            'industry': industry,
            'signal_count': result.get('signal_count', 0),
            'avg_return': metric.get('avg_return'),
            'win_rate': metric.get('win_rate'),
            'exit_avg_return': exit_metrics.get('avg_return'),
            'exit_win_rate': exit_metrics.get('win_rate'),
            'dominant_style': dominant_style,
            'trend_tier': trend_tier,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        print({'status': 'no_result'})
        raise SystemExit(0)

    summary = df.groupby('trend_tier').agg(
        sample_count=('ts_code', 'count'),
        avg_return=('avg_return', 'mean'),
        avg_win_rate=('win_rate', 'mean'),
        avg_exit_return=('exit_avg_return', 'mean'),
        avg_exit_win_rate=('exit_win_rate', 'mean'),
    ).reset_index()
    priority_df = df[df['trend_tier'] == '主线趋势-优先'].copy()
    print({
        'status': 'ok',
        'summary': summary.to_dict(orient='records'),
        'priority_top': priority_df.sort_values('avg_return', ascending=False).head(15).to_dict(orient='records'),
        'priority_bottom': priority_df.sort_values('avg_return', ascending=True).head(15).to_dict(orient='records'),
    })
