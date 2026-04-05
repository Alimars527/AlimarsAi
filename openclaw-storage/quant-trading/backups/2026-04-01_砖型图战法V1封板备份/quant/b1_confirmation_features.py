import pandas as pd


def add_b1_confirmation_features(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    out = df.copy()
    close = pd.to_numeric(out.get('close'), errors='coerce')
    open_ = pd.to_numeric(out.get('open'), errors='coerce')
    high = pd.to_numeric(out.get('high'), errors='coerce')
    low = pd.to_numeric(out.get('low'), errors='coerce')
    vol = pd.to_numeric(out.get('vol'), errors='coerce')
    prev_vol = vol.shift(1)
    pct = pd.to_numeric(out.get('pct_chg'), errors='coerce')
    white = pd.to_numeric(out.get('white_line'), errors='coerce') if 'white_line' in out.columns else pd.Series(index=out.index, dtype='float64')
    yellow = pd.to_numeric(out.get('yellow_line'), errors='coerce') if 'yellow_line' in out.columns else pd.Series(index=out.index, dtype='float64')

    full_range = (high - low).replace(0, pd.NA)
    upper_shadow = (high - pd.concat([close, open_], axis=1).max(axis=1)).clip(lower=0)
    body = (close - open_).abs()

    out['b1_confirm_volume'] = (vol >= prev_vol * 1.15).fillna(False)
    out['b1_confirm_close_quality'] = ((body / full_range) >= 0.35).fillna(False)
    out['b1_confirm_upper_shadow_ok'] = ((upper_shadow / full_range) <= 0.35).fillna(False)
    out['b1_confirm_white_hold'] = (close >= white).fillna(False)
    out['b1_confirm_yellow_hold'] = (close >= yellow).fillna(False)
    out['b1_confirm_pullback_ok'] = ((pct > -2.5) & (pct < 6.5)).fillna(False)
    out['b1_confirm_followthrough'] = (
        out['b1_confirm_volume'].fillna(False)
        & out['b1_confirm_close_quality'].fillna(False)
        & out['b1_confirm_upper_shadow_ok'].fillna(False)
    )

    out['b1_confirm_score'] = 0
    for col in [
        'b1_confirm_volume',
        'b1_confirm_close_quality',
        'b1_confirm_upper_shadow_ok',
        'b1_confirm_white_hold',
        'b1_confirm_yellow_hold',
        'b1_confirm_pullback_ok',
        'b1_confirm_followthrough',
    ]:
        out.loc[out[col].fillna(False), 'b1_confirm_score'] += 1

    out['b1_confirm_pass'] = out['b1_confirm_score'] >= 4
    out['b1_strong_confirm_pass'] = out['b1_confirm_score'] >= 6
    return out
