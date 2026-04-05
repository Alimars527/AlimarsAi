import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.batch_backtest import BatchBacktester
from quant.trend_tier_map import normalize_trend_tier
from quant.hkhold_policy import hkhold_policy_for_industry

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


def load_latest_hkhold_metrics(code: str):
    path = project_root / 'data' / 'hkhold' / f'{code}.csv'
    if not path.exists():
        return {
            'hkhold_available': False,
            'hkhold_ratio': 0.0,
            'hkhold_ratio_change': 0.0,
            'hkhold_positive_5': 0.0,
        }
    df = pd.read_csv(path, dtype=str)
    if df.empty or 'trade_date' not in df.columns or 'ratio' not in df.columns:
        return {
            'hkhold_available': False,
            'hkhold_ratio': 0.0,
            'hkhold_ratio_change': 0.0,
            'hkhold_positive_5': 0.0,
        }
    df['ratio'] = pd.to_numeric(df['ratio'], errors='coerce')
    df = df.sort_values('trade_date').drop_duplicates(subset=['trade_date'], keep='last')
    df['ratio_change'] = df['ratio'].diff()
    df['positive_5'] = (df['ratio_change'] > 0).rolling(5).sum()
    latest = df.iloc[-1]
    return {
        'hkhold_available': True,
        'hkhold_ratio': float(latest.get('ratio', 0) or 0),
        'hkhold_ratio_change': float(latest.get('ratio_change', 0) or 0),
        'hkhold_positive_5': float(latest.get('positive_5', 0) or 0),
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
        hk = load_latest_hkhold_metrics(code)
        policy = hkhold_policy_for_industry(
            industry,
            hk['hkhold_ratio'],
            hk['hkhold_ratio_change'],
            hk['hkhold_positive_5'],
        )
        rows.append({
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
            'hkhold_available': hk['hkhold_available'],
            'hkhold_ratio': hk['hkhold_ratio'],
            'hkhold_ratio_change': hk['hkhold_ratio_change'],
            'hkhold_positive_5': hk['hkhold_positive_5'],
            'hkhold_score': policy['hkhold_score'],
            'hkhold_reason': policy['hkhold_reason'],
        })

    df = pd.DataFrame(rows)
    clean = df[(df['trend_tier'] == '主线趋势-优先') & (df['industry'].isin(ALLOWED_INDUSTRIES))].copy()
    high = clean[clean['hkhold_score'] >= 1.0].copy()
    low = clean[clean['hkhold_score'] < 1.0].copy()

    summary = {
        'sample_count': int(len(clean)),
        'hkhold_score_ge_1_count': int(len(high)),
        'hkhold_score_lt_1_count': int(len(low)),
        'hkhold_score_ge_1_avg_return': round(float(high['avg_return'].mean()), 4) if not high.empty else None,
        'hkhold_score_ge_1_avg_exit_return': round(float(high['avg_exit_return'].mean()), 4) if not high.empty else None,
        'hkhold_score_lt_1_avg_return': round(float(low['avg_return'].mean()), 4) if not low.empty else None,
        'hkhold_score_lt_1_avg_exit_return': round(float(low['avg_exit_return'].mean()), 4) if not low.empty else None,
    }

    print({
        'status': 'ok',
        'summary': summary,
        'high_score_group': high.sort_values('avg_return', ascending=False).to_dict(orient='records'),
        'low_score_group': low.sort_values('avg_return', ascending=False).to_dict(orient='records'),
    })
