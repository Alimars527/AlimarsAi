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


def load_latest_margin_metrics(code: str):
    path = project_root / 'data' / 'margin_detail' / f'{code}.csv'
    if not path.exists():
        return {'margin_available': False, 'margin_net_buy_5': 0.0, 'margin_positive_days_5': 0.0, 'margin_rzye_change_5': 0.0}
    df = pd.read_csv(path, dtype=str)
    if df.empty or 'trade_date' not in df.columns:
        return {'margin_available': False, 'margin_net_buy_5': 0.0, 'margin_positive_days_5': 0.0, 'margin_rzye_change_5': 0.0}
    for col in ['rzye', 'rzmre', 'rzche']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.sort_values('trade_date').drop_duplicates(subset=['trade_date'], keep='last')
    if 'rzmre' in df.columns and 'rzche' in df.columns:
        df['margin_net_buy'] = df['rzmre'] - df['rzche']
        df['margin_net_buy_5'] = df['margin_net_buy'].rolling(5).sum()
        df['margin_positive_days_5'] = (df['margin_net_buy'] > 0).rolling(5).sum()
    if 'rzye' in df.columns:
        df['margin_rzye_change_5'] = df['rzye'].diff(5)
    latest = df.iloc[-1]
    return {
        'margin_available': True,
        'margin_net_buy_5': float(latest.get('margin_net_buy_5', 0) or 0),
        'margin_positive_days_5': float(latest.get('margin_positive_days_5', 0) or 0),
        'margin_rzye_change_5': float(latest.get('margin_rzye_change_5', 0) or 0),
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
        mg = load_latest_margin_metrics(code)
        rows.append({
            'ts_code': code,
            'name': name,
            'industry': industry,
            'signal_count': result.get('signal_count', 0),
            'avg_return': metric.get('avg_return'),
            'avg_exit_return': exit_metric.get('avg_return'),
            'trend_tier': trend_tier,
            **mg,
        })
    df = pd.DataFrame(rows)
    clean = df[(df['trend_tier'] == '主线趋势-优先') & (df['industry'].isin(ALLOWED_INDUSTRIES))].copy()
    pos = clean[(clean['margin_net_buy_5'] > 0) & (clean['margin_positive_days_5'] >= 3)].copy()
    non = clean[~((clean['margin_net_buy_5'] > 0) & (clean['margin_positive_days_5'] >= 3))].copy()
    summary = {
        'sample_count': int(len(clean)),
        'positive_margin_group': int(len(pos)),
        'non_positive_margin_group': int(len(non)),
        'positive_margin_avg_return': round(float(pos['avg_return'].mean()), 4) if not pos.empty else None,
        'positive_margin_avg_exit_return': round(float(pos['avg_exit_return'].mean()), 4) if not pos.empty else None,
        'non_positive_margin_avg_return': round(float(non['avg_return'].mean()), 4) if not non.empty else None,
        'non_positive_margin_avg_exit_return': round(float(non['avg_exit_return'].mean()), 4) if not non.empty else None,
    }
    print({'status': 'ok', 'summary': summary, 'positive_margin_group_rows': pos.to_dict(orient='records')})
