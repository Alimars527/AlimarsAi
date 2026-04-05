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


def enrich_hkhold_metrics(code: str):
    hk_path = project_root / 'data' / 'hkhold' / f'{code}.csv'
    if not hk_path.exists():
        return {
            'hkhold_available': False,
            'avg_hkhold_ratio': None,
            'avg_hkhold_ratio_change': None,
            'avg_hkhold_positive_5': None,
        }
    hk = pd.read_csv(hk_path, dtype=str)
    if hk.empty or 'trade_date' not in hk.columns:
        return {
            'hkhold_available': False,
            'avg_hkhold_ratio': None,
            'avg_hkhold_ratio_change': None,
            'avg_hkhold_positive_5': None,
        }
    hk['ratio'] = pd.to_numeric(hk.get('ratio'), errors='coerce')
    hk = hk.sort_values('trade_date').drop_duplicates(subset=['trade_date'], keep='last')
    hk['ratio_change'] = hk['ratio'].diff()
    hk['ratio_positive_5'] = (hk['ratio_change'] > 0).rolling(5).sum()
    return {
        'hkhold_available': True,
        'avg_hkhold_ratio': round(float(hk['ratio'].dropna().mean()), 4) if hk['ratio'].notna().any() else None,
        'avg_hkhold_ratio_change': round(float(hk['ratio_change'].dropna().mean()), 6) if hk['ratio_change'].notna().any() else None,
        'avg_hkhold_positive_5': round(float(hk['ratio_positive_5'].dropna().mean()), 4) if hk['ratio_positive_5'].notna().any() else None,
    }


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
        row = {
            'ts_code': code,
            'name': name,
            'industry': industry,
            'signal_count': result.get('signal_count', 0),
            'avg_return': metric.get('avg_return'),
            'avg_win_rate': metric.get('win_rate'),
            'avg_exit_return': exit_metric.get('avg_return'),
            'avg_exit_win_rate': exit_metric.get('win_rate'),
            'dominant_style': dominant_style,
            'trend_tier': trend_tier,
        }
        row.update(enrich_hkhold_metrics(code))
        rows.append(row)

    out = pd.DataFrame(rows)
    clean = out[(out['trend_tier'] == '主线趋势-优先') & (out['industry'].isin(ALLOWED_INDUSTRIES))].copy()
    available = clean[clean['hkhold_available'] == True].copy()
    unavailable = clean[clean['hkhold_available'] != True].copy()
    summary = {
        'total_sample': int(len(clean)),
        'hkhold_available_sample': int(len(available)),
        'hkhold_unavailable_sample': int(len(unavailable)),
        'available_avg_return': round(float(available['avg_return'].mean()), 4) if not available.empty else None,
        'available_avg_exit_return': round(float(available['avg_exit_return'].mean()), 4) if not available.empty else None,
        'unavailable_avg_return': round(float(unavailable['avg_return'].mean()), 4) if not unavailable.empty else None,
        'unavailable_avg_exit_return': round(float(unavailable['avg_exit_return'].mean()), 4) if not unavailable.empty else None,
    }
    print({
        'status': 'ok',
        'summary': summary,
        'top_hkhold_ratio': available.sort_values('avg_hkhold_ratio', ascending=False).head(20).to_dict(orient='records') if not available.empty else [],
        'top_hkhold_positive_5': available.sort_values('avg_hkhold_positive_5', ascending=False).head(20).to_dict(orient='records') if not available.empty else [],
    })
