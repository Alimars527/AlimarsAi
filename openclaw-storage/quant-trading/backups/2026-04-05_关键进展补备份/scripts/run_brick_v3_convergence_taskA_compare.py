#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quant.indicators import add_tactic_base_indicators
from quant.brick_formula import add_brick_formula_flags

START_DATE = '20230101'
END_DATE = '20260403'
PROGRESS_PATH = ROOT / 'outputs' / 'brick_v3_convergence_taskA_progress.json'
RESULT_PATH = ROOT / 'outputs' / 'brick_v3_convergence_taskA_summary.json'
COMPARE_PATH = ROOT / 'outputs' / 'brick_v3_convergence_taskA_compare.csv'
YEARLY_PATH = ROOT / 'outputs' / 'brick_v3_convergence_taskA_yearly.csv'
TAIL_PATH = ROOT / 'outputs' / 'brick_v3_convergence_taskA_tail_risk.csv'
EVENTS_PATH = ROOT / 'outputs' / 'brick_v3_convergence_taskA_events.csv'


VARIANTS = {
    'V3_BASE': {
        'desc': '砖型图V3基线版',
        'position_max_white_ratio': None,
        'position_max_pressure_ratio': None,
        'quality_red_vs_prev_green_ratio': 1.0,
        'quality_white_yellow_gap_min': 0.0,
        'quality_green_decay_ratio_max': None,
        'rotation_rank_max': 5,
        'warn_extra_strict': False,
    },
    'V3_A1_POS_LIGHT': {
        'desc': '位置轻收束：close<=white*1.03',
        'position_max_white_ratio': 1.03,
        'position_max_pressure_ratio': None,
        'quality_red_vs_prev_green_ratio': 1.0,
        'quality_white_yellow_gap_min': 0.0,
        'quality_green_decay_ratio_max': None,
        'rotation_rank_max': 5,
        'warn_extra_strict': False,
    },
    'V3_A1_POS_MED': {
        'desc': '位置中收束：close<=white*1.02 且 close<=pressure*0.97',
        'position_max_white_ratio': 1.02,
        'position_max_pressure_ratio': 0.97,
        'quality_red_vs_prev_green_ratio': 1.0,
        'quality_white_yellow_gap_min': 0.0,
        'quality_green_decay_ratio_max': None,
        'rotation_rank_max': 5,
        'warn_extra_strict': False,
    },
    'V3_A2_QUALITY_LIGHT': {
        'desc': '质量轻收束：红砖>=前绿砖*1.05 + 白黄差>=0.3%',
        'position_max_white_ratio': None,
        'position_max_pressure_ratio': None,
        'quality_red_vs_prev_green_ratio': 1.05,
        'quality_white_yellow_gap_min': 0.003,
        'quality_green_decay_ratio_max': None,
        'rotation_rank_max': 5,
        'warn_extra_strict': False,
    },
    'V3_A2_QUALITY_MED': {
        'desc': '质量中收束：红砖>=前绿砖*1.1 + 白黄差>=0.8% + 最后一绿砖<=首绿砖85%',
        'position_max_white_ratio': None,
        'position_max_pressure_ratio': None,
        'quality_red_vs_prev_green_ratio': 1.10,
        'quality_white_yellow_gap_min': 0.008,
        'quality_green_decay_ratio_max': 0.85,
        'rotation_rank_max': 5,
        'warn_extra_strict': False,
    },
    'V3_A3_WARN_STRICT': {
        'desc': '环境细分：转弱仅允许更强结构 + 行业Top3',
        'position_max_white_ratio': None,
        'position_max_pressure_ratio': None,
        'quality_red_vs_prev_green_ratio': 1.0,
        'quality_white_yellow_gap_min': 0.0,
        'quality_green_decay_ratio_max': None,
        'rotation_rank_max': 5,
        'warn_extra_strict': True,
    },
}


def save_progress(status, total, done, message=''):
    pct = round(done / total * 100, 2) if total else 100.0
    PROGRESS_PATH.write_text(json.dumps({
        'task': 'brick_v3_convergence_taskA_compare',
        'status': status,
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_codes': total,
        'completed_codes': done,
        'progress_pct': pct,
        'message': message,
    }, ensure_ascii=False, indent=2), encoding='utf-8')


def trimmed_mean(vals, trim_ratio):
    arr = sorted([float(x) for x in vals if pd.notna(x)])
    n = len(arr)
    if n == 0:
        return 0.0
    k = int(n * trim_ratio)
    core = arr[k:n-k] if 2 * k < n else arr
    return round(sum(core) / len(core), 4) if core else 0.0


def summarize_returns(series: pd.Series):
    s = pd.to_numeric(series, errors='coerce').dropna()
    if s.empty:
        return {
            'event_count': 0, 'signal_days': 0, 'win_rate': 0.0, 'avg_return': 0.0,
            'median_return': 0.0, 'trimmed_mean_10': 0.0, 'trimmed_mean_20': 0.0,
            'max_loss': 0.0, 'worst_5pct_mean': 0.0,
        }
    q5 = s.quantile(0.05)
    tail = s[s <= q5]
    return {
        'event_count': int(len(s)),
        'win_rate': round((s > 0).mean() * 100, 2),
        'avg_return': round(s.mean(), 4),
        'median_return': round(s.median(), 4),
        'trimmed_mean_10': trimmed_mean(s.tolist(), 0.10),
        'trimmed_mean_20': trimmed_mean(s.tolist(), 0.20),
        'max_loss': round(s.min(), 4),
        'worst_5pct_mean': round(tail.mean(), 4) if not tail.empty else 0.0,
    }


def build_rotation_board(meta):
    rows = []
    for row in meta[['ts_code', 'industry']].itertuples(index=False):
        p = ROOT / 'data' / 'daily' / f'{row.ts_code}.csv'
        if not p.exists() or not row.industry:
            continue
        try:
            df = pd.read_csv(p, usecols=['trade_date', 'pct_chg'], dtype={'trade_date': str})
            df = df[(df['trade_date'] >= START_DATE) & (df['trade_date'] <= END_DATE)].copy()
            if df.empty:
                continue
            df['pct_chg'] = pd.to_numeric(df['pct_chg'], errors='coerce')
            df['industry'] = row.industry
            rows.append(df[['trade_date', 'industry', 'pct_chg']])
        except Exception:
            continue
    ind = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=['trade_date', 'industry', 'pct_chg'])
    board = ind.groupby(['trade_date', 'industry'], as_index=False)['pct_chg'].mean().sort_values(['trade_date', 'pct_chg'], ascending=[True, False])
    board['rank'] = board.groupby('trade_date')['pct_chg'].rank(method='first', ascending=False)
    return board


def base_signal_ok(df, idx, industry, board_rank_map, omav_map):
    td = str(df.iloc[idx]['trade_date'])
    env = omav_map.get(td)
    if not env:
        return False
    if bool(env['omav_bear_regime_flag']):
        return False
    rank = board_rank_map.get((td, industry))
    if rank is None or rank > 5:
        return False
    z = pd.to_numeric(df['brick_formula_value'], errors='coerce').fillna(0)
    green = df['brick_formula_green'].fillna(False).astype(bool)
    xg = df['brick_raw_turn_red'].fillna(False).astype(bool)
    white = pd.to_numeric(df['white_line'], errors='coerce')
    yellow = pd.to_numeric(df['yellow_line'], errors='coerce')
    high = pd.to_numeric(df['high'], errors='coerce')
    return bool(
        idx >= 4
        and xg.iloc[idx]
        and bool(df['brick_history_ok'].fillna(False).astype(bool).iloc[idx])
        and pd.notna(white.iloc[idx]) and pd.notna(yellow.iloc[idx]) and pd.notna(high.iloc[idx])
        and high.iloc[idx] >= white.iloc[idx]
        and white.iloc[idx] > yellow.iloc[idx]
        and green.iloc[idx-1] and green.iloc[idx-2] and green.iloc[idx-3] and green.iloc[idx-4]
        and (z.iloc[idx-4] > z.iloc[idx-3] > z.iloc[idx-2] > z.iloc[idx-1])
        and (z.iloc[idx] >= z.iloc[idx-1])
    )


def variant_ok(df, idx, industry, board_rank_map, omav_map, conf):
    if not base_signal_ok(df, idx, industry, board_rank_map, omav_map):
        return False
    td = str(df.iloc[idx]['trade_date'])
    env = omav_map.get(td, {})
    rotation_warn = bool(env.get('omav_rotation_warning_flag', False))
    rank = board_rank_map.get((td, industry), 999)

    close = float(pd.to_numeric(df.iloc[idx]['close'], errors='coerce'))
    white = float(pd.to_numeric(df.iloc[idx]['white_line'], errors='coerce'))
    yellow = float(pd.to_numeric(df.iloc[idx]['yellow_line'], errors='coerce'))
    pressure = float(pd.to_numeric(df.iloc[max(0, idx-9):idx+1]['high'], errors='coerce').max())

    z = pd.to_numeric(df['brick_formula_value'], errors='coerce').fillna(0)
    red_strength = float(z.iloc[idx]) / float(z.iloc[idx-1]) if float(z.iloc[idx-1]) > 0 else 999
    green_decay_last_vs_first = float(z.iloc[idx-1]) / float(z.iloc[idx-4]) if float(z.iloc[idx-4]) > 0 else 999
    white_gap_ratio = (white - yellow) / abs(yellow) if yellow else 0.0

    if conf['position_max_white_ratio'] is not None and close > white * conf['position_max_white_ratio']:
        return False
    if conf['position_max_pressure_ratio'] is not None and close > pressure * conf['position_max_pressure_ratio']:
        return False
    if red_strength < conf['quality_red_vs_prev_green_ratio']:
        return False
    if white_gap_ratio < conf['quality_white_yellow_gap_min']:
        return False
    if conf['quality_green_decay_ratio_max'] is not None and green_decay_last_vs_first > conf['quality_green_decay_ratio_max']:
        return False

    rank_limit = conf['rotation_rank_max']
    if conf['warn_extra_strict'] and rotation_warn:
        rank_limit = 3
        if red_strength < 1.08:
            return False
        if white_gap_ratio < 0.005:
            return False
        if close > white * 1.02:
            return False
    if rank > rank_limit:
        return False
    return True


def main():
    meta = pd.read_csv(ROOT / 'data' / 'meta' / 'stock_basic.csv', dtype=str).fillna('')
    meta = meta[~meta['ts_code'].astype(str).str.endswith('.BJ')]
    meta = meta[~meta['name'].astype(str).str.contains('ST', case=False, na=False)]
    meta = meta[~meta['industry'].astype(str).isin(['银行'])]
    meta = meta[~meta['industry'].astype(str).str.contains('房地产', na=False)]

    omav = pd.read_csv(ROOT / 'data' / 'omav' / 'omav_daily_standardized_20260402.csv', dtype={'trade_date': str})
    omav = omav[(omav['trade_date'] >= START_DATE) & (omav['trade_date'] <= END_DATE)].copy()
    omav['omav_rotation_warning_flag'] = omav['omav_rotation_warning_flag'].astype(str).str.lower().eq('true')
    omav['omav_bear_regime_flag'] = omav['omav_bear_regime_flag'].astype(str).str.lower().eq('true')
    omav_map = omav.set_index('trade_date')[['omav_rotation_warning_flag', 'omav_bear_regime_flag']].to_dict('index')

    board = build_rotation_board(meta)
    board_rank_map = board.set_index(['trade_date', 'industry'])['rank'].to_dict()

    total = len(meta)
    done = 0
    save_progress('running', total, 0, 'building variants')
    events = []

    for row in meta[['ts_code', 'name', 'industry']].itertuples(index=False):
        p = ROOT / 'data' / 'daily' / f'{row.ts_code}.csv'
        if not p.exists():
            done += 1
            continue
        try:
            df = pd.read_csv(p, dtype={'trade_date': str}).sort_values('trade_date').reset_index(drop=True)
            if df.empty or len(df) < 260 or not {'trade_date', 'open', 'high', 'low', 'close'}.issubset(df.columns):
                done += 1
                continue
            df = add_tactic_base_indicators(df)
            df = add_brick_formula_flags(df)
            df = df[(df['trade_date'] >= START_DATE) & (df['trade_date'] <= END_DATE)].reset_index(drop=True)
            for idx in range(len(df) - 4):
                for variant_name, conf in VARIANTS.items():
                    if not variant_ok(df, idx, row.industry, board_rank_map, omav_map, conf):
                        continue
                    c0 = float(df.iloc[idx]['close'])
                    o1 = float(df.iloc[idx+1]['open'])
                    l1 = float(df.iloc[idx+1]['low'])
                    entry = min(c0 * 0.995, o1 * 0.99)
                    if l1 > entry:
                        continue
                    exit_close = float(df.iloc[idx+1]['close'])
                    ret = (exit_close / entry - 1) * 100 if entry > 0 else None
                    events.append({
                        'variant': variant_name,
                        'variant_desc': conf['desc'],
                        'signal_date': str(df.iloc[idx]['trade_date']),
                        'year': str(df.iloc[idx]['trade_date'])[:4],
                        'code': row.ts_code,
                        'name': row.name,
                        'industry': row.industry,
                        'entry_price': round(entry, 4),
                        'exit_price': round(exit_close, 4),
                        'return_pct': round(ret, 4) if ret is not None else None,
                    })
        except Exception:
            pass
        done += 1
        if done % 100 == 0 or done == total:
            save_progress('running', total, done, f'processed {done}/{total}')

    events_df = pd.DataFrame(events)
    events_df.to_csv(EVENTS_PATH, index=False, encoding='utf-8-sig')

    compare_rows = []
    yearly_rows = []
    tail_rows = []
    result = {'task': 'Task A - 砖型图V3收束优化', 'date_range': [START_DATE, END_DATE], 'variants': {}}

    for variant_name, conf in VARIANTS.items():
        sub = events_df[events_df['variant'] == variant_name].copy() if not events_df.empty else pd.DataFrame()
        summary = summarize_returns(sub['return_pct'] if not sub.empty else pd.Series(dtype=float))
        signal_days = int(sub['signal_date'].nunique()) if not sub.empty else 0
        summary['signal_days'] = signal_days
        summary['variant_desc'] = conf['desc']
        result['variants'][variant_name] = summary

        compare_rows.append({'variant': variant_name, 'variant_desc': conf['desc'], **summary})

        if not sub.empty:
            for year, ydf in sub.groupby('year'):
                ys = summarize_returns(ydf['return_pct'])
                yearly_rows.append({'variant': variant_name, 'year': year, **ys, 'signal_days': int(ydf['signal_date'].nunique())})
            worst10 = sub.sort_values('return_pct', ascending=True).head(10)
            tail_rows.append({
                'variant': variant_name,
                'worst_trade': round(float(worst10['return_pct'].min()), 4),
                'worst_10_avg': round(float(worst10['return_pct'].mean()), 4),
                'worst_5pct_mean': summary['worst_5pct_mean'],
            })
        else:
            tail_rows.append({'variant': variant_name, 'worst_trade': 0.0, 'worst_10_avg': 0.0, 'worst_5pct_mean': 0.0})

    pd.DataFrame(compare_rows).to_csv(COMPARE_PATH, index=False, encoding='utf-8-sig')
    pd.DataFrame(yearly_rows).to_csv(YEARLY_PATH, index=False, encoding='utf-8-sig')
    pd.DataFrame(tail_rows).to_csv(TAIL_PATH, index=False, encoding='utf-8-sig')

    result.update({
        'compare_path': str(COMPARE_PATH),
        'yearly_path': str(YEARLY_PATH),
        'tail_risk_path': str(TAIL_PATH),
        'events_path': str(EVENTS_PATH),
    })
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save_progress('completed', total, total, 'done')
    print(RESULT_PATH)


if __name__ == '__main__':
    main()
