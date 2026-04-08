import pandas as pd


def add_single_pin_low20_flags(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    out = df.copy()
    open_ = pd.to_numeric(out.get('open'), errors='coerce')
    high = pd.to_numeric(out.get('high'), errors='coerce')
    low = pd.to_numeric(out.get('low'), errors='coerce')
    close = pd.to_numeric(out.get('close'), errors='coerce')
    vol = pd.to_numeric(out.get('vol'), errors='coerce')

    body = (close - open_).abs()
    full_range = (high - low).replace(0, pd.NA)
    lower_shadow = (pd.concat([open_, close], axis=1).min(axis=1) - low)
    upper_shadow = (high - pd.concat([open_, close], axis=1).max(axis=1))

    low20 = low.rolling(20).min()
    vol5 = vol.rolling(5).mean()
    white = pd.to_numeric(out.get('white_line'), errors='coerce') if 'white_line' in out.columns else close.rolling(10).mean()
    yellow = pd.to_numeric(out.get('yellow_line'), errors='coerce') if 'yellow_line' in out.columns else close.rolling(20).mean()

    needle_like = (lower_shadow >= body * 1.5) & (lower_shadow >= upper_shadow)
    stable_close = close >= open_ * 0.99
    near_low20 = low <= low20 * 1.03
    vol_ok = vol >= vol5 * 0.8

    out['single_pin_low20'] = (needle_like & stable_close & near_low20 & vol_ok).fillna(False)
    out['single_pin_four_zero'] = False
    out['single_pin_white_cross_red'] = ((close >= white * 0.995) & (open_ <= white * 1.01)).fillna(False)
    out['single_pin_white_cross_yellow'] = ((close >= yellow * 0.995) & (open_ <= yellow * 1.01)).fillna(False)
    return out
