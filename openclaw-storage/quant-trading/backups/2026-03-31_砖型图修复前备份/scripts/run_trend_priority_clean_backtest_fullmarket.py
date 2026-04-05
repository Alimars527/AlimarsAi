import sys
import json
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.batch_backtest import BatchBacktester
from quant.trend_tier_map import normalize_trend_tier

ALLOWED_INDUSTRIES = {'元器件', '电气设备', '软件服务'}
PROGRESS_EVERY = 200
PROGRESS_PATH = project_root / 'outputs' / 'fullmarket_backtest_progress.json'
RESULT_PATH = project_root / 'outputs' / 'fullmarket_backtest_latest.json'


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


def write_progress(processed, total, qualified, status='running'):
    payload = {
        'status': status,
        'processed': int(processed),
        'total': int(total),
        'qualified': int(qualified),
        'progress_pct': round(processed / total, 4) if total else 0,
    }
    PROGRESS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"progress {processed}/{total} qualified={qualified}")


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
        if result.get('status') != 'ok':
            if idx % PROGRESS_EVERY == 0:
                qualified = len([x for x in rows if x['trend_tier'] == '主线趋势-优先' and x['industry'] in ALLOWED_INDUSTRIES])
                write_progress(idx, total, qualified)
            continue
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
            qualified = len([x for x in rows if x['trend_tier'] == '主线趋势-优先' and x['industry'] in ALLOWED_INDUSTRIES])
            write_progress(idx, total, qualified)

    df = pd.DataFrame(rows)
    if df.empty:
        out = {'status': 'no_result', 'universe_count': int(total)}
        RESULT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
        write_progress(total, total, 0, status='done')
        print(out)
        raise SystemExit(0)

    clean_df = df[(df['trend_tier'] == '主线趋势-优先') & (df['industry'].isin(ALLOWED_INDUSTRIES))].copy()
    summary = {
        'sample_count': int(len(clean_df)),
        'avg_return': round(float(clean_df['avg_return'].dropna().mean()), 4) if not clean_df.empty else None,
        'avg_win_rate': round(float(clean_df['win_rate'].dropna().mean()), 4) if not clean_df.empty else None,
        'avg_exit_return': round(float(clean_df['exit_avg_return'].dropna().mean()), 4) if not clean_df.empty else None,
        'avg_exit_win_rate': round(float(clean_df['exit_win_rate'].dropna().mean()), 4) if not clean_df.empty else None,
        'industries': sorted(clean_df['industry'].dropna().unique().tolist()) if not clean_df.empty else [],
    }
    by_industry = clean_df.groupby('industry').agg(
        sample_count=('ts_code', 'count'),
        avg_return=('avg_return', 'mean'),
        avg_win_rate=('win_rate', 'mean'),
        avg_exit_return=('exit_avg_return', 'mean'),
        avg_exit_win_rate=('exit_win_rate', 'mean'),
    ).reset_index() if not clean_df.empty else pd.DataFrame()

    out = {
        'status': 'ok',
        'universe_count': int(total),
        'qualified_count': int(len(clean_df)),
        'summary': summary,
        'by_industry': by_industry.to_dict(orient='records') if not by_industry.empty else [],
        'top': clean_df.sort_values('avg_return', ascending=False).head(20).to_dict(orient='records') if not clean_df.empty else [],
        'bottom': clean_df.sort_values('avg_return', ascending=True).head(20).to_dict(orient='records') if not clean_df.empty else [],
    }
    RESULT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    write_progress(total, total, len(clean_df), status='done')
    print(out)
