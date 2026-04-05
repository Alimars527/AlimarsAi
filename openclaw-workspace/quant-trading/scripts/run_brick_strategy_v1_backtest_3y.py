#!/usr/bin/env python3
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quant.indicators import add_tactic_base_indicators
from quant.brick_formula import add_brick_formula_flags

START_DATE = '20230101'
END_DATE = '20260331'
MAX_HOLD_RED_BRICKS = 4

PROGRESS_PATH = ROOT / 'outputs' / 'brick_strategy_v1_backtest_3y_progress.json'
RESULT_PATH = ROOT / 'outputs' / 'brick_strategy_v1_backtest_3y.json'
EVENTS_PATH = ROOT / 'outputs' / 'brick_strategy_v1_backtest_3y_events.csv'
ANNUAL_BOARD_PATH = ROOT / 'outputs' / 'brick_strategy_v1_backtest_3y_annual_board.csv'
MONTHLY_BOARD_PATH = ROOT / 'outputs' / 'brick_strategy_v1_backtest_3y_monthly_board.csv'
ANNUAL_INDUSTRY_TOP5_PATH = ROOT / 'outputs' / 'brick_strategy_v1_backtest_3y_annual_industry_top5.csv'
MONTHLY_INDUSTRY_TOP3_PATH = ROOT / 'outputs' / 'brick_strategy_v1_backtest_3y_monthly_industry_top3.csv'


def save_progress(status, total, done):
    pct = round(done / total * 100, 2) if total else 100.0
    PROGRESS_PATH.write_text(json.dumps({
        'task': 'brick_strategy_v1_backtest_3y',
        'status': status,
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_codes': total,
        'completed_codes': done,
        'progress_pct': pct,
        'start_date': START_DATE,
        'end_date': END_DATE,
    }, ensure_ascii=False, indent=2), encoding='utf-8')


def build_signal(df: pd.DataFrame) -> pd.Series:
    z = pd.to_numeric(df['brick_formula_value'], errors='coerce').fillna(0)
    green = df['brick_formula_green'].fillna(False).astype(bool)
    xg = df['brick_raw_turn_red'].fillna(False).astype(bool)
    white = pd.to_numeric(df['white_line'], errors='coerce')
    yellow = pd.to_numeric(df['yellow_line'], errors='coerce')
    high = pd.to_numeric(df['high'], errors='coerce')
    return (
        xg
        & (high >= white)
        & (white > yellow)
        & green.shift(1, fill_value=False)
        & green.shift(2, fill_value=False)
        & green.shift(3, fill_value=False)
        & green.shift(4, fill_value=False)
        & (z.shift(4) > z.shift(3))
        & (z.shift(3) > z.shift(2))
        & (z.shift(2) > z.shift(1))
        & (z >= z.shift(1))
        & df['brick_history_ok'].fillna(False).astype(bool)
    )


def simulate_trade(df: pd.DataFrame, idx: int):
    if idx + 1 >= len(df):
        return None
    entry_i = idx + 1
    entry_date = str(df.iloc[entry_i]['trade_date'])
    entry_price = float(df.iloc[entry_i]['open'])
    if pd.isna(entry_price) or entry_price <= 0:
        return None

    red_seen = 0
    exit_i = None
    exit_reason = 'end_of_data'

    for j in range(entry_i, len(df)):
        row = df.iloc[j]
        open_px = float(row['open'])
        close_px = float(row['close'])
        brick_val = float(row['brick_formula_value'])
        prev_brick_val = float(df.iloc[j - 1]['brick_formula_value']) if j > 0 else brick_val
        green_brick = bool(row['brick_formula_green'])
        red_brick = brick_val > prev_brick_val

        # 止损1：买入次日开盘没有大幅拉升就减仓/离场，先按保守离场建模
        if j == entry_i + 1:
            gap_pct = (open_px / entry_price - 1) * 100 if entry_price else 0
            if gap_pct < 2.0:
                exit_i = j
                exit_reason = 'next_day_open_no_surge'
                break

        if red_brick:
            red_seen += 1
        if green_brick:
            exit_i = j
            exit_reason = 'green_brick_exit'
            break
        if red_seen >= 4:
            exit_i = j
            exit_reason = 'max_4_red_bricks'
            break

    if exit_i is None:
        exit_i = len(df) - 1
    exit_date = str(df.iloc[exit_i]['trade_date'])
    exit_price = float(df.iloc[exit_i]['close'])
    ret = (exit_price / entry_price - 1) * 100 if entry_price else None
    return {
        'signal_date': str(df.iloc[idx]['trade_date']),
        'entry_date': entry_date,
        'exit_date': exit_date,
        'entry_price': entry_price,
        'exit_price': exit_price,
        'return_pct': ret,
        'holding_days': int(exit_i - entry_i + 1),
        'exit_reason': exit_reason,
    }


def summarize(df: pd.DataFrame, period_col: str):
    if df.empty:
        return pd.DataFrame(columns=[period_col, 'event_count', 'signal_days', 'avg_symbols_per_signal_day', 'win_rate', 'avg_return_pct', 'median_return_pct'])
    g = df.groupby(period_col)
    out = g.agg(
        event_count=('code', 'count'),
        signal_days=('signal_date', 'nunique'),
        win_rate=('return_pct', lambda s: round((pd.to_numeric(s, errors='coerce') > 0).mean() * 100, 2)),
        avg_return_pct=('return_pct', lambda s: round(pd.to_numeric(s, errors='coerce').mean(), 4)),
        median_return_pct=('return_pct', lambda s: round(pd.to_numeric(s, errors='coerce').median(), 4)),
    ).reset_index()
    out['avg_symbols_per_signal_day'] = (out['event_count'] / out['signal_days']).round(4)
    return out


def industry_rank(df: pd.DataFrame, period_col: str, topn: int):
    if df.empty:
        return pd.DataFrame(columns=[period_col, 'industry', 'event_count', 'win_rate', 'avg_return_pct', 'rank'])
    g = df.groupby([period_col, 'industry']).agg(
        event_count=('code', 'count'),
        win_rate=('return_pct', lambda s: round((pd.to_numeric(s, errors='coerce') > 0).mean() * 100, 2)),
        avg_return_pct=('return_pct', lambda s: round(pd.to_numeric(s, errors='coerce').mean(), 4)),
    ).reset_index()
    g['rank'] = g.groupby(period_col)['avg_return_pct'].rank(method='first', ascending=False)
    return g[g['rank'] <= topn].sort_values([period_col, 'rank', 'industry'])


def main():
    meta = pd.read_csv(ROOT / 'data' / 'meta' / 'stock_basic.csv', dtype=str).fillna('')
    meta = meta[~meta['ts_code'].astype(str).str.endswith('.BJ')]
    meta = meta[~meta['name'].astype(str).str.contains('ST', case=False, na=False)]

    total = len(meta)
    done = 0
    save_progress('running', total, done)

    events = []
    for row in meta[['ts_code', 'name', 'industry']].itertuples(index=False):
        p = ROOT / 'data' / 'daily' / f'{row.ts_code}.csv'
        done += 1
        if done % 100 == 0 or done == total:
            save_progress('running', total, done)
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p, usecols=['trade_date', 'open', 'high', 'low', 'close'], dtype={'trade_date': str})
            if df.empty or len(df) < 260:
                continue
            df = df.sort_values('trade_date').reset_index(drop=True)
            df = add_tactic_base_indicators(df)
            df = add_brick_formula_flags(df)
            df = df[(df['trade_date'] >= START_DATE) & (df['trade_date'] <= END_DATE)].reset_index(drop=True)
            if df.empty:
                continue
            sig = build_signal(df)
            hit_idx = df.index[sig].tolist()
            for idx in hit_idx:
                trade = simulate_trade(df, idx)
                if not trade:
                    continue
                trade.update({
                    'code': row.ts_code,
                    'name': row.name,
                    'industry': row.industry,
                    'year': trade['signal_date'][:4],
                    'month': trade['signal_date'][:6],
                })
                events.append(trade)
        except Exception:
            continue

    events_df = pd.DataFrame(events)
    events_df.to_csv(EVENTS_PATH, index=False, encoding='utf-8-sig')

    annual = summarize(events_df, 'year')
    monthly = summarize(events_df, 'month')
    annual_top5 = industry_rank(events_df, 'year', 5)
    monthly_top3 = industry_rank(events_df, 'month', 3)

    annual.to_csv(ANNUAL_BOARD_PATH, index=False, encoding='utf-8-sig')
    monthly.to_csv(MONTHLY_BOARD_PATH, index=False, encoding='utf-8-sig')
    annual_top5.to_csv(ANNUAL_INDUSTRY_TOP5_PATH, index=False, encoding='utf-8-sig')
    monthly_top3.to_csv(MONTHLY_INDUSTRY_TOP3_PATH, index=False, encoding='utf-8-sig')

    result = {
        'strategy': 'brick_strategy_v1',
        'date_range': [START_DATE, END_DATE],
        'summary': {
            'event_count': int(len(events_df)),
            'signal_days': int(events_df['signal_date'].nunique()) if not events_df.empty else 0,
            'win_rate': round((pd.to_numeric(events_df['return_pct'], errors='coerce') > 0).mean() * 100, 2) if not events_df.empty else 0,
            'avg_return_pct': round(pd.to_numeric(events_df['return_pct'], errors='coerce').mean(), 4) if not events_df.empty else 0,
            'median_return_pct': round(pd.to_numeric(events_df['return_pct'], errors='coerce').median(), 4) if not events_df.empty else 0,
        },
        'annual_board_path': str(ANNUAL_BOARD_PATH),
        'monthly_board_path': str(MONTHLY_BOARD_PATH),
        'annual_industry_top5_path': str(ANNUAL_INDUSTRY_TOP5_PATH),
        'monthly_industry_top3_path': str(MONTHLY_INDUSTRY_TOP3_PATH),
        'events_path': str(EVENTS_PATH),
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save_progress('completed', total, total)
    print(RESULT_PATH)
    print(ANNUAL_BOARD_PATH)
    print(MONTHLY_BOARD_PATH)
    print(ANNUAL_INDUSTRY_TOP5_PATH)
    print(MONTHLY_INDUSTRY_TOP3_PATH)


if __name__ == '__main__':
    main()
