from typing import Optional

import pandas as pd

from .b1_experimental_v1 import b1_experimental_v1_ok, safe_num


def _load_omav_avg5_prev(project_root, trade_date: str):
    p = project_root / 'data' / 'omav' / 'omav_daily_standardized_20260402.csv'
    if not p.exists():
        return None
    df = pd.read_csv(p, dtype={'trade_date': str}).sort_values('trade_date').reset_index(drop=True)
    omav = safe_num(df.get('omav'))
    if omav.isna().all() and 'omav_value' in df.columns:
        omav = safe_num(df.get('omav_value'))
    df['avg5_prev'] = omav.shift(1).rolling(5).mean()
    hit = df[df['trade_date'].astype(str) == str(trade_date)]
    if hit.empty:
        return None
    v = pd.to_numeric(hit.iloc[-1].get('avg5_prev'), errors='coerce')
    return None if pd.isna(v) else float(v)


def b1_experimental_v4b_ok(df: pd.DataFrame, idx: Optional[int] = None, project_root=None) -> bool:
    if not b1_experimental_v1_ok(df, idx):
        return False
    if df is None or df.empty:
        return False
    if idx is None:
        idx = len(df) - 1
    if idx < 2:
        return False

    prev1_pct = pd.to_numeric(df.iloc[idx - 1].get('pct_chg'), errors='coerce')
    prev2_pct = pd.to_numeric(df.iloc[idx - 2].get('pct_chg'), errors='coerce')
    if pd.notna(prev1_pct) and pd.notna(prev2_pct):
        if float(prev1_pct) <= -1.5 and float(prev2_pct) <= -1.5:
            return False

    # V4-B 的环境层是轻降权，不是硬过滤；候选链仍视作命中
    return True


def b1_v4b_deweight_hit(df: pd.DataFrame, idx: Optional[int] = None, project_root=None) -> bool:
    if df is None or df.empty or project_root is None:
        return False
    if idx is None:
        idx = len(df) - 1
    trade_date = str(df.iloc[idx].get('trade_date'))
    avg5_prev = _load_omav_avg5_prev(project_root, trade_date)
    if avg5_prev is None:
        return False
    return 1 < float(avg5_prev) <= 2
