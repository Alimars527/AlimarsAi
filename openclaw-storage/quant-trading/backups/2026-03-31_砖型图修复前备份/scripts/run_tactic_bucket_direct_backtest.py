import sys
import json
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.batch_backtest import BatchBacktester
from quant.indicators import add_tactic_base_indicators
from quant.b1_perfect_features import add_b1_perfect_features
from quant.b1_b2_signals import detect_b1_b2_signals
from quant.weekly_signals import detect_week_b1
from quant.single_pin_bucket import add_single_pin_low20_flags
from quant.brick_bucket import add_brick_flags
from quant.brick_formula import add_brick_formula_flags
from quant.ultra_short_execution import add_open_execution_proxies, evaluate_ultra_short_next_day
from quant.tactic_router import route_tactic

OUT = project_root / 'outputs' / 'tactic_bucket_direct_backtest_2026-03-23.json'
PROGRESS = project_root / 'outputs' / 'tactic_bucket_direct_backtest_progress.json'
STATE = project_root / 'outputs' / 'tactic_bucket_direct_backtest_state.jsonl'
PROGRESS_EVERY = 200


def write_progress(processed, total, rows_count, status='running'):
    payload = {
        'status': status,
        'processed': int(processed),
        'total': int(total),
        'rows_count': int(rows_count),
        'progress_pct': round(processed / total, 4) if total else 0,
    }
    PROGRESS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


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


def prepare_direct_tactic_item(backtester, code, name, industry):
    df = backtester._prepare_daily_frame(code, industry=industry)
    if df is None or df.empty or len(df) < 25:
        return None

    df = add_tactic_base_indicators(df)
    df = add_b1_perfect_features(df)
    df = detect_b1_b2_signals(df)
    df = add_single_pin_low20_flags(df)
    df = add_brick_flags(df)
    df = add_brick_formula_flags(df)
    df = add_open_execution_proxies(df)
    df = evaluate_ultra_short_next_day(df)
    weekly_df = detect_week_b1(df)

    latest = df.iloc[-2].copy()
    next_row = df.iloc[-1].copy()
    latest_week_b1 = bool(weekly_df.iloc[-2].get('week_b1', False)) if len(weekly_df) >= 2 else False

    close_now = pd.to_numeric(latest.get('close'), errors='coerce')
    close_next = pd.to_numeric(next_row.get('close'), errors='coerce')
    if pd.isna(close_now) or pd.isna(close_next) or close_now == 0:
        return None

    next_return = (close_next / close_now - 1) * 100
    is_ultra_short = bool(
        latest.get('single_pin_low20', False)
        or latest.get('brick_exec_ready', False)
        or latest.get('brick_red_turn', False)
        or latest.get('brick_formula_signal', False)
    )
    eval_return = float(next_row.get('ultra_short_exit_return', next_return)) if is_ultra_short else float(next_return)
    eval_win = 1.0 if eval_return > 0 else 0.0

    if bool(latest.get('open_exec_ok', False)):
        execution_style = '开盘观察后可执行'
    elif bool(latest.get('open_exec_watch_extend', False)):
        execution_style = '9:33后继续观察'
    else:
        execution_style = '开盘放弃或谨慎'

    item = {
        'code': code,
        'name': name,
        'industry': industry,
        'trend_tier': '技术备选',
        'strategy_tag': '技术备选',
        'execution_style': execution_style,
        'reason': '',
        'pct_chg': float(latest.get('pct_chg', 0) or 0),
        'secondary_confirm_tier': '',
        'day_b1': bool(latest.get('day_b1', False)),
        'week_b1': latest_week_b1,
        'b2_signal': bool(latest.get('b2_signal', False)),
        'b1_strength': int(latest.get('b1_strength', 0) or 0),
        'b2_strength': int(latest.get('b2_strength', 0) or 0),
        'b2_shape_ready': bool(latest.get('b2_shape_ready', False)),
        'b2_volume_double': bool(latest.get('b2_volume_double', False)),
        'perfect_b1': bool(latest.get('perfect_b1', False)),
        'standard_b1': bool(latest.get('standard_b1', False)),
        'weak_b1': bool(latest.get('weak_b1', False)),
        'b1_base_for_b2': bool(latest.get('b1_base_for_b2', False)),
        'true_weak_b1': bool(latest.get('true_weak_b1', False)),
        'b1_confirm_pass': bool(latest.get('b1_confirm_pass', False)),
        'b1_strong_confirm_pass': bool(latest.get('b1_strong_confirm_pass', False)),
        'b1_confirm_score': int(latest.get('b1_confirm_score', 0) or 0),
        'b1_confirm_capital_pass': bool(latest.get('b1_confirm_capital_pass', False)),
        'b1_strong_confirm_capital_pass': bool(latest.get('b1_strong_confirm_capital_pass', False)),
        'b1_confirm_capital_score': int(latest.get('b1_confirm_capital_score', 0) or 0),
        'b1_confirm_context_pass': bool(latest.get('b1_confirm_context_pass', False)),
        'b1_strong_confirm_context_pass': bool(latest.get('b1_strong_confirm_context_pass', False)),
        'b1_confirm_context_score': int(latest.get('b1_confirm_context_score', 0) or 0),
        'b1_confirm_capital_context_pass': bool(latest.get('b1_confirm_capital_context_pass', False)),
        'b1_research_industry_pool': bool(latest.get('b1_research_industry_pool', False)),
        'b1_confirm_non_brick_pass': bool(latest.get('b1_confirm_non_brick_pass', False)),
        'b1_confirm_capital_industry_pass': bool(latest.get('b1_confirm_capital_industry_pass', False)),
        'b1_confirm_capital_industry_non_brick_pass': bool(latest.get('b1_confirm_capital_industry_non_brick_pass', False)),
        'single_pin_low20': bool(latest.get('single_pin_low20', False)),
        'single_pin_four_zero': bool(latest.get('single_pin_four_zero', False)),
        'single_pin_white_cross_red': bool(latest.get('single_pin_white_cross_red', False)),
        'single_pin_white_cross_yellow': bool(latest.get('single_pin_white_cross_yellow', False)),
        'brick_exec_ready': bool(latest.get('brick_exec_ready', False)),
        'brick_red_turn': bool(latest.get('brick_red_turn', False)),
        'brick_green_turn': bool(latest.get('brick_green_turn', False)),
        'brick_formula_signal': bool(latest.get('brick_formula_signal', False)),
        'brick_formula_strong_signal': bool(latest.get('brick_formula_strong_signal', False)),
        'brick_formula_turn_red': bool(latest.get('brick_formula_turn_red', False)),
        'open_exec_ok': bool(latest.get('open_exec_ok', False)),
        'open_exec_watch_extend': bool(latest.get('open_exec_watch_extend', False)),
        'ultra_short_take_profit_hit': bool(next_row.get('ultra_short_take_profit_hit', False)),
        'ultra_short_red_next_day': bool(next_row.get('ultra_short_red_next_day', False)),
        'avg_return': eval_return,
        'win_rate': eval_win,
        'exit_avg_return': eval_return,
        'exit_win_rate': eval_win,
    }
    return route_tactic(item)


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
        item = prepare_direct_tactic_item(runner.backtester, code, name, industry)
        if item is not None:
            item['_idx'] = offset
            rows.append(item)
            append_state(item)
        if offset % PROGRESS_EVERY == 0:
            write_progress(offset, total, len(rows))

    df = pd.DataFrame(rows)
    out = {'status': 'ok', 'universe_count': int(total), 'result_count': int(len(df)), 'by_tactic': [], 'by_hit': []}
    if not df.empty:
        for col in ['avg_return', 'win_rate', 'exit_avg_return', 'exit_win_rate']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        bucket_df = df.copy()
        if 'tactic_buckets' in bucket_df.columns:
            bucket_df = bucket_df.explode('tactic_buckets')
            bucket_df['tactic_bucket'] = bucket_df['tactic_buckets']
        by_tactic = bucket_df.groupby(['tactic_bucket']).agg(
            sample_count=('code', 'count'),
            avg_return=('avg_return', 'mean'),
            avg_win_rate=('win_rate', 'mean'),
            avg_exit_return=('exit_avg_return', 'mean'),
            avg_exit_win_rate=('exit_win_rate', 'mean'),
        ).reset_index().sort_values(['sample_count', 'avg_return'], ascending=[False, False])
        out['by_tactic'] = by_tactic.to_dict(orient='records')

        hit_fields = [
            ('hit_b1', 'B1命中'),
            ('hit_b1_perfect', '完美B1命中'),
            ('hit_b1_standard', '标准B1命中'),
            ('hit_b1_weak', '弱B1命中'),
            ('hit_b1_base_for_b2', 'B1底座型命中'),
            ('hit_true_weak_b1', '真弱B1命中'),
            ('b1_confirm_pass', 'B1二次确认通过'),
            ('b1_strong_confirm_pass', 'B1强化确认通过'),
            ('hit_b2', 'B2命中'),
            ('hit_brick', '砖型图命中'),
            ('hit_single_pin', '单针命中'),
        ]
        hit_rows = []
        for field, label in hit_fields:
            if field not in df.columns:
                continue
            sub = df[df[field] == True].copy()
            if sub.empty:
                continue
            hit_rows.append({
                'hit_field': field,
                'hit_label': label,
                'sample_count': int(len(sub)),
                'avg_return': float(sub['avg_return'].mean()),
                'avg_win_rate': float(sub['win_rate'].mean()),
                'avg_exit_return': float(sub['exit_avg_return'].mean()),
                'avg_exit_win_rate': float(sub['exit_win_rate'].mean()),
            })
        out['by_hit'] = hit_rows

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    write_progress(total, total, len(rows), status='done')
    print(out)
