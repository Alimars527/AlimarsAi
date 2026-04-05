import pandas as pd


def add_open_execution_proxies(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()

    open_ = pd.to_numeric(out.get('open'), errors='coerce')
    high = pd.to_numeric(out.get('high'), errors='coerce')
    low = pd.to_numeric(out.get('low'), errors='coerce')
    close = pd.to_numeric(out.get('close'), errors='coerce')
    prev_close = close.shift(1)

    open_gap = (open_ / prev_close - 1.0) * 100
    intraday_draw_from_open = (low / open_ - 1.0) * 100
    intraday_push_from_open = (high / open_ - 1.0) * 100
    close_vs_open = (close / open_ - 1.0) * 100

    out['open_gap_pct'] = open_gap
    out['open_chase_risk'] = open_gap >= 3.0
    out['open_smash_risk'] = open_gap <= -3.0
    out['open_pullback_exists'] = intraday_draw_from_open <= -0.8
    out['open_reclaim_strength'] = close_vs_open >= 0
    out['open_exec_ok'] = (
        (~out['open_chase_risk'].fillna(False))
        & (~out['open_smash_risk'].fillna(False))
        & out['open_pullback_exists'].fillna(False)
        & out['open_reclaim_strength'].fillna(False)
    )
    out['open_exec_watch_extend'] = (
        (~out['open_chase_risk'].fillna(False))
        & (~out['open_smash_risk'].fillna(False))
        & (intraday_push_from_open <= 4.0).fillna(False)
    )
    return out


def evaluate_ultra_short_next_day(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    open_ = pd.to_numeric(out.get('open'), errors='coerce')
    high = pd.to_numeric(out.get('high'), errors='coerce')
    close = pd.to_numeric(out.get('close'), errors='coerce')
    prev_close = close.shift(1)

    next_day_high_gain = (high / prev_close - 1.0) * 100
    next_day_close_gain = (close / prev_close - 1.0) * 100
    out['next_day_high_gain'] = next_day_high_gain
    out['next_day_close_gain'] = next_day_close_gain

    out['ultra_short_take_profit_hit'] = next_day_high_gain >= 5.0
    out['ultra_short_red_next_day'] = next_day_close_gain > 0
    out['ultra_short_exit_return'] = next_day_close_gain
    out.loc[out['ultra_short_take_profit_hit'].fillna(False), 'ultra_short_exit_return'] = 5.0
    out['ultra_short_partial_take_profit'] = out['ultra_short_take_profit_hit'].fillna(False)
    out['ultra_short_fail_exit'] = (~out['ultra_short_red_next_day'].fillna(False))
    return out
