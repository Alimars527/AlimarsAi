import sys
import json
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.batch_backtest import BatchBacktester
from quant.trend_tier_map import normalize_trend_tier
from quant.tactic_router import route_tactic
from quant.indicators import add_tactic_base_indicators
from quant.b1_b2_signals import detect_b1_b2_signals
from quant.weekly_signals import detect_week_b1

OUT = project_root / 'outputs' / 'tactic_group_backtest_refined_2026-03-23.json'
PROGRESS = project_root / 'outputs' / 'tactic_group_backtest_refined_progress.json'
STATE = project_root / 'outputs' / 'tactic_group_backtest_refined_state.jsonl'
PROGRESS_EVERY = 200


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


def write_progress(processed, total, rows_count, status='running'):
    payload = {
        'status': status,
        'processed': int(processed),
        'total': int(total),
        'rows_count': int(rows_count),
        'progress_pct': round(processed / total, 4) if total else 0,
    }
    PROGRESS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"progress {processed}/{total} rows={rows_count}")


def prepare_signal_flags(backtester, code, industry):
    df = backtester._prepare_daily_frame(code, industry=industry)
    if df is None or df.empty:
        return {}
    df = add_tactic_base_indicators(df)
    df = detect_b1_b2_signals(df)
    weekly_df = detect_week_b1(df)
    latest = df.iloc[-1]
    latest_week_b1 = bool(weekly_df.iloc[-1].get('week_b1', False)) if not weekly_df.empty else False
    return {
        'day_b1': bool(latest.get('day_b1', False)),
        'week_b1': latest_week_b1,
        'b2_signal': bool(latest.get('b2_signal', False)),
        'b1_strength': int(latest.get('b1_strength', 0) or 0),
        'b2_strength': int(latest.get('b2_strength', 0) or 0),
        'single_pin_low20': bool(latest.get('single_pin_low20', False)),
        'single_pin_four_zero': bool(latest.get('single_pin_four_zero', False)),
        'single_pin_white_cross_red': bool(latest.get('single_pin_white_cross_red', False)),
        'single_pin_white_cross_yellow': bool(latest.get('single_pin_white_cross_yellow', False)),
        'brick_exec_ready': bool(latest.get('brick_exec_ready', False)),
        'brick_red_turn': bool(latest.get('brick_red_turn', False)),
        'brick_green_turn': bool(latest.get('brick_green_turn', False)),
    }


def load_state():
    if not STATE.exists():
        return 0, []
    rows = []
    last_index = 0
    with STATE.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            last_index = max(last_index, int(obj.get('_idx', 0)))
            rows.append(obj)
    return last_index, rows


def append_state(item):
    with STATE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    runner = BatchBacktester(project_root)
    universe = runner.filter_universe(runner.load_universe())
    total = len(universe)
    last_index, rows = load_state()
    write_progress(last_index, total, len(rows))

    iterable = universe.iloc[last_index:]
    for offset, (_, r) in enumerate(iterable.iterrows(), start=last_index + 1):
        code = r['ts_code']
        name = r.get('name', '')
        industry = r.get('industry', '')
        result = runner.backtester.run_single_code(code, strategy_name='主线趋势', hold_days=1, industry=industry)
        if result.get('status') != 'ok':
            if offset % PROGRESS_EVERY == 0:
                write_progress(offset, total, len(rows))
            continue
        style_counts = result.get('style_counts', {})
        dominant_style = dominant_style_from_counts(style_counts)
        trend_tier = normalize_trend_tier(dominant_style)
        metric = result.get('metrics', {})
        exit_metrics = result.get('exit_metrics', {})
        signal_flags = prepare_signal_flags(runner.backtester, code, industry)
        item = {
            '_idx': offset,
            'code': code,
            'name': name,
            'industry': industry,
            'trend_tier': trend_tier,
            'strategy_tag': '主线趋势' if trend_tier in ['主线趋势-优先', '主线趋势-谨慎'] else '技术备选',
            'execution_style': '主线趋势，可重点观察' if trend_tier == '主线趋势-优先' else '可做埋伏观察',
            'reason': '',
            'pct_chg': 0,
            'secondary_confirm_tier': '',
            'avg_return': metric.get('avg_return'),
            'win_rate': metric.get('win_rate'),
            'exit_avg_return': exit_metrics.get('avg_return'),
            'exit_win_rate': exit_metrics.get('win_rate'),
            'signal_count': result.get('signal_count', 0),
        }
        item.update(signal_flags)
        item = route_tactic(item)
        rows.append(item)
        append_state(item)
        if offset % PROGRESS_EVERY == 0:
            write_progress(offset, total, len(rows))

    df = pd.DataFrame(rows)
    for col in ['avg_return', 'win_rate', 'exit_avg_return', 'exit_win_rate']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    by_tactic = df.groupby(['tactic_bucket', 'tactic_family', 'tactic_signal']).agg(
        sample_count=('code', 'count'),
        avg_return=('avg_return', 'mean'),
        avg_win_rate=('win_rate', 'mean'),
        avg_exit_return=('exit_avg_return', 'mean'),
        avg_exit_win_rate=('exit_win_rate', 'mean'),
    ).reset_index().sort_values(['avg_return', 'avg_win_rate'], ascending=[False, False])
    out = {
        'status': 'ok',
        'universe_count': int(total),
        'result_count': int(len(df)),
        'by_tactic': by_tactic.to_dict(orient='records'),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    write_progress(total, total, len(rows), status='done')
    print(out)
