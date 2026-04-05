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
    universe = universe[universe['industry'] == TARGET_INDUSTRY].head(160)
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

        df = runner.backtester._prepare_daily_frame(code, industry=TARGET_INDUSTRY)
        metric = result.get('metrics', {})
        exit_metric = result.get('exit_metrics', {})
        if df.empty:
            continue
        rows.append({
            'ts_code': code,
            'name': name,
            'signal_count': result.get('signal_count', 0),
            'avg_return': metric.get('avg_return'),
            'win_rate': metric.get('win_rate'),
            'exit_avg_return': exit_metric.get('avg_return'),
            'exit_win_rate': exit_metric.get('win_rate'),
            'avg_volatility_10': round(float(pd.to_numeric(df['volatility_10'], errors='coerce').dropna().mean()), 4) if 'volatility_10' in df.columns else None,
            'avg_strong_days_10': round(float(pd.to_numeric(df['strong_days_10'], errors='coerce').dropna().mean()), 4) if 'strong_days_10' in df.columns else None,
            'avg_mf_strength': round(float(pd.to_numeric(df['mf_strength'], errors='coerce').dropna().mean()), 6) if 'mf_strength' in df.columns else None,
            'avg_mf_positive_days_5': round(float(pd.to_numeric(df['mf_positive_days_5'], errors='coerce').dropna().mean()), 4) if 'mf_positive_days_5' in df.columns else None,
            'dominant_style': dominant_style,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        print({'status': 'empty'})
        raise SystemExit(0)

    bad = df[df['exit_avg_return'] < -0.5].copy()
    good = df[df['exit_avg_return'] > 0.5].copy()

    def group_summary(sub, label):
        if sub.empty:
            return {'label': label, 'count': 0}
        return {
            'label': label,
            'count': int(len(sub)),
            'avg_signal_count': round(float(sub['signal_count'].mean()), 2),
            'avg_return': round(float(sub['avg_return'].mean()), 4),
            'avg_exit_return': round(float(sub['exit_avg_return'].mean()), 4),
            'avg_win_rate': round(float(sub['win_rate'].mean()), 4),
            'avg_exit_win_rate': round(float(sub['exit_win_rate'].mean()), 4),
            'avg_volatility_10': round(float(sub['avg_volatility_10'].mean()), 4),
            'avg_strong_days_10': round(float(sub['avg_strong_days_10'].mean()), 4),
            'avg_mf_strength': round(float(sub['avg_mf_strength'].mean()), 6),
            'avg_mf_positive_days_5': round(float(sub['avg_mf_positive_days_5'].mean()), 4),
        }

    print({
        'status': 'ok',
        'summary': [
            group_summary(bad, 'bad_components'),
            group_summary(good, 'good_components'),
        ],
        'bad_examples': bad.sort_values('exit_avg_return').head(15).to_dict(orient='records'),
        'good_examples': good.sort_values('exit_avg_return', ascending=False).head(15).to_dict(orient='records'),
    })
