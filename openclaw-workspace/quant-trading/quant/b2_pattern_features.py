import pandas as pd


def add_b2_pattern_features(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    close = pd.to_numeric(out['close'], errors='coerce')
    open_ = pd.to_numeric(out['open'], errors='coerce')
    high = pd.to_numeric(out['high'], errors='coerce')
    low = pd.to_numeric(out['low'], errors='coerce')
    vol = pd.to_numeric(out['vol'], errors='coerce')

    prev_close = close.shift(1)
    prev_vol = vol.shift(1)

    # 实体与上影
    body = (close - open_).abs()
    upper_shadow = high - pd.concat([close, open_], axis=1).max(axis=1)
    full_range = (high - low).replace(0, pd.NA)

    out['b2_gt_4pct'] = pd.to_numeric(out.get('pct_chg'), errors='coerce') > 4
    out['b2_volume_expand'] = vol > prev_vol
    out['b2_volume_double'] = vol >= prev_vol * 2
    out['b2_strong_body'] = ((body / full_range) > 0.35).fillna(False)
    out['b2_short_upper_shadow'] = ((upper_shadow / full_range) < 0.25).fillna(False)

    # B1之后：最近若干日出现过 B1
    if 'day_b1' in out.columns:
        recent_b1 = out['day_b1'].shift(1).rolling(10).max().fillna(False)
        out['b2_after_b1'] = recent_b1.astype(bool)
    else:
        out['b2_after_b1'] = False

    # 回调或横盘整理：近几日涨幅不大 / 缩量
    recent_ret = close.pct_change().rolling(3).sum()
    out['b2_after_consolidation'] = ((recent_ret.abs() < 0.08) | (vol < vol.rolling(5).mean())).fillna(False)

    # 第一版可计算 B2 形态信号
    out['b2_shape_ready'] = (
        out['b2_after_b1'].fillna(False)
        & out['b2_after_consolidation'].fillna(False)
        & out['b2_gt_4pct'].fillna(False)
        & out['b2_volume_expand'].fillna(False)
        & out['b2_strong_body'].fillna(False)
        & out['b2_short_upper_shadow'].fillna(False)
    )

    out['b2_shape_strength'] = 0
    out.loc[out['b2_after_b1'].fillna(False), 'b2_shape_strength'] += 1
    out.loc[out['b2_after_consolidation'].fillna(False), 'b2_shape_strength'] += 1
    out.loc[out['b2_gt_4pct'].fillna(False), 'b2_shape_strength'] += 1
    out.loc[out['b2_volume_expand'].fillna(False), 'b2_shape_strength'] += 1
    out.loc[out['b2_volume_double'].fillna(False), 'b2_shape_strength'] += 1
    out.loc[out['b2_strong_body'].fillna(False), 'b2_shape_strength'] += 1
    out.loc[out['b2_short_upper_shadow'].fillna(False), 'b2_shape_strength'] += 1

    return out
