import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.batch_backtest import BatchBacktester
from quant.trend_tier_map import normalize_trend_tier

TARGET_INDUSTRY = '元器件'


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
    universe = universe[universe['industry'] == TARGET_INDUSTRY].head(120)
    rows = []
    for _, r in universe.iterrows():
        code = r['ts_code']
        name = r.get('name', '')
        result = runner.backtester.run_single_code(code, strategy_name='主线趋势', hold_days=1, industry=TARGET_INDUSTRY)
        if result.get('status') != 'ok':
            continue
        style_counts = result.get('style_counts', {})
        dominant_style = dominant_style_from_counts(style_counts)
        trend_tier = normalize_trend_tier(dominant_style)
        if trend_tier != '主线趋势-优先':
            continue
        metric = result.get('metrics', {})
        exit_metric = result.get('exit_metrics', {})
        rows.append({
            'ts_code': code,
            'name': name,
            'signal_count': result.get('signal_count', 0),
            'avg_return': metric.get('avg_return'),
            'win_rate': metric.get('win_rate'),
            'exit_avg_return': exit_metric.get('avg_return'),
            'exit_win_rate': exit_metric.get('win_rate'),
            'dominant_style': dominant_style,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        print({'status': 'empty'})
    else:
        print({
            'status': 'ok',
            'summary': {
                'sample_count': int(len(df)),
                'avg_return': round(float(df['avg_return'].dropna().mean()), 4),
                'avg_win_rate': round(float(df['win_rate'].dropna().mean()), 4),
                'avg_exit_return': round(float(df['exit_avg_return'].dropna().mean()), 4),
                'avg_exit_win_rate': round(float(df['exit_win_rate'].dropna().mean()), 4),
            },
            'worst': df.sort_values('exit_avg_return', ascending=True).head(12).to_dict(orient='records'),
            'best': df.sort_values('exit_avg_return', ascending=False).head(12).to_dict(orient='records'),
        })
