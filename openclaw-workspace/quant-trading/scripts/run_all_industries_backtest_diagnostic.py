import sys
import json
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.batch_backtest import BatchBacktester
from quant.trend_tier_map import normalize_trend_tier

PROGRESS_EVERY = 200
PROGRESS_PATH = project_root / 'outputs' / 'all_industries_backtest_progress.json'
RESULT_PATH = project_root / 'outputs' / 'all_industries_backtest_latest.json'


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


def write_progress(processed, total, result_count, status='running'):
    payload = {
        'status': status,
        'processed': int(processed),
        'total': int(total),
        'result_count': int(result_count),
        'progress_pct': round(processed / total, 4) if total else 0,
    }
    PROGRESS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"progress {processed}/{total} results={result_count}")


if __name__ == '__main__':
    runner = BatchBacktester(project_root)
    universe = runner.filter_universe(runner.load_universe())
    rows = []
    total = len(universe)
    write_progress(0, total, 0)

    for idx, (_, r) in enumerate(universe.iterrows(), start=1):
        code = r['ts_code']
        name = r.get('name', '')
        industry = r.get('industry', '')
        result = runner.backtester.run_single_code(code, strategy_name='主线趋势', hold_days=1, industry=industry)
        if result.get('status') == 'ok':
            style_counts = result.get('style_counts', {})
            dominant_style = dominant_style_from_counts(style_counts)
            trend_tier = normalize_trend_tier(dominant_style)
            metric = result.get('metrics', {})
            exit_metrics = result.get('exit_metrics', {})
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
        if idx % PROGRESS_EVERY == 0:
            write_progress(idx, total, len(rows))

    df = pd.DataFrame(rows)
    if df.empty:
        out = {'status': 'no_result', 'universe_count': int(total)}
        RESULT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
        write_progress(total, total, 0, status='done')
        print(out)
        raise SystemExit(0)

    by_industry = df.groupby('industry').agg(
        sample_count=('ts_code', 'count'),
        avg_return=('avg_return', 'mean'),
        avg_win_rate=('win_rate', 'mean'),
        avg_exit_return=('exit_avg_return', 'mean'),
        avg_exit_win_rate=('exit_win_rate', 'mean'),
    ).reset_index()
    by_industry = by_industry.sort_values(['avg_return', 'avg_win_rate'], ascending=[False, False]).reset_index(drop=True)

    by_tier = df.groupby('trend_tier').agg(
        sample_count=('ts_code', 'count'),
        avg_return=('avg_return', 'mean'),
        avg_win_rate=('win_rate', 'mean'),
        avg_exit_return=('exit_avg_return', 'mean'),
        avg_exit_win_rate=('exit_win_rate', 'mean'),
    ).reset_index().sort_values('avg_return', ascending=False)

    out = {
        'status': 'ok',
        'universe_count': int(total),
        'result_count': int(len(df)),
        'industry_count': int(by_industry['industry'].nunique()),
        'tier_count': int(by_tier['trend_tier'].nunique()),
        'overall': {
            'avg_return': round(float(df['avg_return'].dropna().mean()), 4),
            'avg_win_rate': round(float(df['win_rate'].dropna().mean()), 4),
            'avg_exit_return': round(float(df['exit_avg_return'].dropna().mean()), 4),
            'avg_exit_win_rate': round(float(df['exit_win_rate'].dropna().mean()), 4),
        },
        'top_industries': by_industry.head(50).to_dict(orient='records'),
        'bottom_industries': by_industry.tail(50).sort_values(['avg_return', 'avg_win_rate'], ascending=[True, True]).to_dict(orient='records'),
        'by_tier': by_tier.to_dict(orient='records'),
    }
    RESULT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    write_progress(total, total, len(df), status='done')
    print(out)
