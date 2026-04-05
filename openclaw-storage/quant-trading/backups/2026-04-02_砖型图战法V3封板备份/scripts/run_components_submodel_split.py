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


def classify_components_submodel(row):
    low_price = float(row.get('avg_close', 0) or 0) < 10
    weak_flow = float(row.get('avg_mf_positive_days_5', 0) or 0) < 1.6
    weak_mf_strength = float(row.get('avg_mf_strength', 0) or 0) < -0.002
    noisy_signal = float(row.get('signal_count', 0) or 0) >= 150
    if (low_price and weak_flow and weak_mf_strength) or (noisy_signal and weak_flow):
        return '低质量趋势元器件'
    return '优质趋势元器件'


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
        if df.empty:
            continue
        metric = result.get('metrics', {})
        exit_metric = result.get('exit_metrics', {})
        item = {
            'ts_code': code,
            'name': name,
            'signal_count': result.get('signal_count', 0),
            'avg_return': metric.get('avg_return'),
            'win_rate': metric.get('win_rate'),
            'exit_avg_return': exit_metric.get('avg_return'),
            'exit_win_rate': exit_metric.get('win_rate'),
            'avg_close': round(float(pd.to_numeric(df['close'], errors='coerce').dropna().mean()), 4),
            'avg_volatility_10': round(float(pd.to_numeric(df['volatility_10'], errors='coerce').dropna().mean()), 4) if 'volatility_10' in df.columns else None,
            'avg_mf_positive_days_5': round(float(pd.to_numeric(df['mf_positive_days_5'], errors='coerce').dropna().mean()), 4) if 'mf_positive_days_5' in df.columns else None,
            'avg_mf_strength': round(float(pd.to_numeric(df['mf_strength'], errors='coerce').dropna().mean()), 6) if 'mf_strength' in df.columns else None,
            'dominant_style': dominant_style,
        }
        item['submodel'] = classify_components_submodel(item)
        rows.append(item)

    out = pd.DataFrame(rows)
    if out.empty:
        print({'status': 'empty'})
        raise SystemExit(0)

    summary = out.groupby('submodel').agg(
        sample_count=('ts_code', 'count'),
        avg_return=('avg_return', 'mean'),
        avg_win_rate=('win_rate', 'mean'),
        avg_exit_return=('exit_avg_return', 'mean'),
        avg_exit_win_rate=('exit_win_rate', 'mean'),
        avg_signal_count=('signal_count', 'mean'),
        avg_close=('avg_close', 'mean'),
        avg_mf_positive_days_5=('avg_mf_positive_days_5', 'mean'),
        avg_mf_strength=('avg_mf_strength', 'mean'),
    ).reset_index()

    print({
        'status': 'ok',
        'summary': summary.to_dict(orient='records'),
        'good_examples': out[out['submodel'] == '优质趋势元器件'].sort_values('exit_avg_return', ascending=False).head(15).to_dict(orient='records'),
        'bad_examples': out[out['submodel'] == '低质量趋势元器件'].sort_values('exit_avg_return', ascending=True).head(15).to_dict(orient='records'),
    })
