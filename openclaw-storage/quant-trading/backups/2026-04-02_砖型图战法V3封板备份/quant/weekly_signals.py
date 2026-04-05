import pandas as pd

from .indicators import add_tactic_base_indicators
from .b1_b2_signals import detect_b1_b2_signals


def resample_to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out['trade_date'] = pd.to_datetime(out['trade_date'].astype(str))
    out = out.sort_values('trade_date')
    weekly = out.resample('W-FRI', on='trade_date').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'vol': 'sum',
        'pct_chg': 'sum',
    }).dropna(subset=['open', 'high', 'low', 'close']).reset_index()
    weekly['trade_date'] = weekly['trade_date'].dt.strftime('%Y%m%d')
    return weekly


def detect_week_b1(df: pd.DataFrame) -> pd.DataFrame:
    weekly = resample_to_weekly(df)
    if weekly.empty:
        return weekly
    weekly = add_tactic_base_indicators(weekly)
    weekly = detect_b1_b2_signals(weekly)
    weekly['week_b1'] = weekly['day_b1'].fillna(False)
    return weekly
