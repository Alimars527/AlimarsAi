import pandas as pd


def add_b1b2_structure_features_relaxed(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    close = pd.to_numeric(out.get('close'), errors='coerce')
    high = pd.to_numeric(out.get('high'), errors='coerce')
    low = pd.to_numeric(out.get('low'), errors='coerce')
    open_ = pd.to_numeric(out.get('open'), errors='coerce')
    vol = pd.to_numeric(out.get('vol'), errors='coerce')

    prev_high_5 = high.shift(1).rolling(5).max()
    prev_high_10 = high.shift(1).rolling(10).max()
    prev_low_5 = low.shift(1).rolling(5).min()
    platform_range = (prev_high_5 - prev_low_5) / prev_high_5.replace(0, pd.NA)
    out['platform_tight_relaxed'] = (platform_range <= 0.18).fillna(False)
    out['restart_near_break_relaxed'] = ((close >= prev_high_5 * 0.985) | (close >= prev_high_10 * 0.98)).fillna(False)

    body = (close - open_).abs()
    full_range = (high - low).replace(0, pd.NA)
    upper_shadow = (high - close.where(close >= open_, open_)).clip(lower=0)
    out['restart_body_relaxed'] = ((body / full_range) >= 0.22).fillna(False)
    out['restart_upper_shadow_relaxed'] = ((upper_shadow / full_range) <= 0.45).fillna(False)

    prev_vol = vol.shift(1).replace(0, pd.NA)
    vol_ratio = vol / prev_vol
    out['restart_volume_relaxed'] = ((vol_ratio >= 1.0) & (vol_ratio <= 3.0)).fillna(False)

    out['b1b2_platform_restart_relaxed'] = (
        out['platform_tight_relaxed']
        & out['restart_near_break_relaxed']
        & out['restart_body_relaxed']
        & out['restart_upper_shadow_relaxed']
        & out['restart_volume_relaxed']
    )
    return out
