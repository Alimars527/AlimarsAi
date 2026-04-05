import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.batch_backtest import BatchBacktester
from quant.trend_tier_map import normalize_trend_tier

ALLOWED_INDUSTRIES = {'元器件', '电气设备', '软件服务'}


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
        style_counts = result.get('style_counts', {})
        dominant_style = dominant_style_from_counts(style_counts)
        trend_tier = normalize_trend_tier(dominant_style)
        metric = result.get('metrics', {})
        exit_metric = result.get('exit_metrics', {})
        sample_signals = result.get('sample_signals', [])
        latest_reason = ' | '.join(sample_signals[-1].get('reason', [])) if sample_signals else ''
        rows.append({
            'ts_code': code,
            'name': name,
            'industry': industry,
            'signal_count': result.get('signal_count', 0),
            'avg_return': metric.get('avg_return'),
            'win_rate': metric.get('win_rate'),
            'exit_avg_return': exit_metric.get('avg_return'),
            'exit_win_rate': exit_metric.get('win_rate'),
            'dominant_style': dominant_style,
            'trend_tier': trend_tier,
            'latest_reason': latest_reason,
            'has_hkhold_reason': ('北向' in latest_reason),
        })
    df = pd.DataFrame(rows)
    clean = df[(df['trend_tier'] == '主线趋势-优先') & (df['industry'].isin(ALLOWED_INDUSTRIES))].copy()
    hk = clean[clean['has_hkhold_reason'] == True].copy()
    non = clean[clean['has_hkhold_reason'] != True].copy()
    summary = {
        'sample_count': int(len(clean)),
        'hkhold_tagged_count': int(len(hk)),
        'non_hkhold_tagged_count': int(len(non)),
        'hkhold_tagged_avg_return': round(float(hk['avg_return'].mean()), 4) if not hk.empty else None,
        'hkhold_tagged_avg_exit_return': round(float(hk['exit_avg_return'].mean()), 4) if not hk.empty else None,
        'non_hkhold_tagged_avg_return': round(float(non['avg_return'].mean()), 4) if not non.empty else None,
        'non_hkhold_tagged_avg_exit_return': round(float(non['exit_avg_return'].mean()), 4) if not non.empty else None,
    }
    print({'status': 'ok', 'summary': summary, 'hkhold_tagged': hk.to_dict(orient='records'), 'non_hkhold_tagged': non.to_dict(orient='records')})
