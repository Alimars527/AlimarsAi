from pathlib import Path
from typing import Set, Tuple

import pandas as pd


def safe_num(v):
    return pd.to_numeric(v, errors='coerce')


def load_omav_flags(project_root: Path, trade_date: str) -> Tuple[bool, bool]:
    p = project_root / 'data' / 'omav' / 'omav_daily_standardized_20260402.csv'
    if not p.exists():
        return False, False
    df = pd.read_csv(p, dtype={'trade_date': str})
    hit = df[df['trade_date'] == str(trade_date)]
    if hit.empty:
        return False, False
    row = hit.iloc[-1]
    warn = str(row.get('omav_rotation_warning_flag', 'False')).lower() == 'true'
    bear = str(row.get('omav_bear_regime_flag', 'False')).lower() == 'true'
    return warn, bear


def build_rotation_top5_set(project_root: Path, trade_date: str) -> Set[str]:
    meta_p = project_root / 'data' / 'meta' / 'stock_basic.csv'
    if not meta_p.exists():
        return set()
    meta = pd.read_csv(meta_p, dtype=str).fillna('')
    rows = []
    for row in meta[['ts_code', 'industry']].itertuples(index=False):
        p = project_root / 'data' / 'daily' / f'{row.ts_code}.csv'
        if not p.exists() or not row.industry:
            continue
        try:
            df = pd.read_csv(p, usecols=['trade_date', 'pct_chg'], dtype={'trade_date': str})
            hit = df[df['trade_date'] == str(trade_date)].copy()
            if hit.empty:
                continue
            hit['pct_chg'] = safe_num(hit['pct_chg'])
            hit['industry'] = row.industry
            rows.append(hit[['trade_date', 'industry', 'pct_chg']])
        except Exception:
            continue
    if not rows:
        return set()
    ind = pd.concat(rows, ignore_index=True)
    board = ind.groupby(['trade_date', 'industry'], as_index=False)['pct_chg'].mean()
    board = board.sort_values(['trade_date', 'pct_chg'], ascending=[True, False])
    board['rank'] = board.groupby('trade_date')['pct_chg'].rank(method='first', ascending=False)
    top5 = board[(board['trade_date'] == str(trade_date)) & (board['rank'] <= 5)].copy()
    return set(top5['industry'].astype(str).tolist())


def brick_v3_strict_hit(df: pd.DataFrame, idx: int, industry: str, project_root: Path, trade_date: str) -> bool:
    if df is None or df.empty or idx < 4:
        return False
    latest = df.iloc[idx]
    white = safe_num(latest.get('white_line'))
    yellow = safe_num(latest.get('yellow_line'))
    high = safe_num(latest.get('high'))
    if pd.isna(white) or pd.isna(yellow) or pd.isna(high):
        return False
    if not (high >= white and white > yellow):
        return False

    if not bool(latest.get('brick_raw_turn_red', False)) or not bool(latest.get('brick_history_ok', False)):
        return False

    if 'brick_formula_value' not in df.columns or 'brick_formula_green' not in df.columns:
        return False
    z = safe_num(df['brick_formula_value']).fillna(0)
    green = df['brick_formula_green'].fillna(False).astype(bool)
    if not bool(green.iloc[idx - 1] and green.iloc[idx - 2] and green.iloc[idx - 3] and green.iloc[idx - 4]):
        return False
    if not bool(z.iloc[idx - 4] > z.iloc[idx - 3] > z.iloc[idx - 2] > z.iloc[idx - 1]):
        return False
    if not bool(z.iloc[idx] >= z.iloc[idx - 1]):
        return False

    warn, bear = load_omav_flags(project_root, trade_date)
    if warn or bear:
        return False

    top5 = build_rotation_top5_set(project_root, trade_date)
    if industry not in top5:
        return False

    return True
