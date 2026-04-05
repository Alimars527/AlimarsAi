import pandas as pd


def add_b1_perfect_features(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()

    close = pd.to_numeric(out['close'], errors='coerce')
    high = pd.to_numeric(out['high'], errors='coerce')
    low = pd.to_numeric(out['low'], errors='coerce')
    open_ = pd.to_numeric(out.get('open'), errors='coerce')
    vol = pd.to_numeric(out.get('vol'), errors='coerce')
    ma20 = close.rolling(20).mean()
    ma30 = close.rolling(30).mean()
    jv = pd.to_numeric(out.get('kdj_j'), errors='coerce') if 'kdj_j' in out.columns else pd.Series(index=out.index, dtype='float64')
    dif = pd.to_numeric(out.get('macd_dif'), errors='coerce') if 'macd_dif' in out.columns else pd.Series(index=out.index, dtype='float64')

    # 回撤：完美层偏浅回调，标准层允许更宽一点
    recent_high_20 = high.rolling(20).max()
    recent_high_30 = high.rolling(30).max()
    drawdown_20 = (recent_high_20 - close) / recent_high_20.replace(0, float('nan'))
    drawdown_30 = (recent_high_30 - close) / recent_high_30.replace(0, float('nan'))
    out['b1_drawdown_ok'] = drawdown_20 <= 0.15
    out['b1_drawdown_relaxed'] = drawdown_30 <= 0.22

    # 回调时间：完美窗口 <=15，标准层允许扩到 <=25 的近似代理
    rolling_low_15 = low.rolling(15).min()
    rolling_low_25 = low.rolling(25).min()
    out['b1_pullback_time_ok'] = low <= rolling_low_15 * 1.02
    out['b1_pullback_time_relaxed'] = low <= rolling_low_25 * 1.03

    # 均线区域：保留为结构加分，不作为标准层硬挡板
    out['b1_ma_zone_ok'] = (close >= ma20) | ((close >= ma30) & (close <= ma20 * 1.02))

    # 连续大阴线排除
    drop_pct = ((open_ - close) / open_.replace(0, float('nan')))
    big_down = ((close < open_) & (drop_pct > 0.04)).fillna(False).astype(bool)
    out['b1_no_continuous_big_down'] = ~(big_down & big_down.shift(1, fill_value=False))

    # 红量推量 / 绿量缩量
    up_day = close > open_
    down_day = close < open_
    out['b1_red_volume_push'] = (up_day & (vol > vol.shift(1))).fillna(False)
    out['b1_green_volume_shrink'] = (down_day & (vol < vol.shift(1))).fillna(False)
    out['b1_volume_structure_ok'] = (
        out['b1_red_volume_push'].rolling(5).max().fillna(False).astype(bool)
        & out['b1_green_volume_shrink'].rolling(5).max().fillna(False).astype(bool)
    )

    # J 值低位
    out['b1_j_low'] = jv <= 20

    # 多周期强化的日线代理：零轴上方延续 or 近端拐头修复
    dif_upturn = ((dif > dif.shift(1)) & (dif.shift(1) <= dif.shift(2))).fillna(False)
    out['b1_multicycle_proxy'] = (((dif > 0) & (dif >= dif.shift(1) * 0.9)) | (dif_upturn & (dif > -0.05))).fillna(False)

    # 完美/标准结构代理
    out['b1_perfect_proxy'] = (
        out['b1_drawdown_ok'].fillna(False)
        & out['b1_pullback_time_ok'].fillna(False)
        & out['b1_no_continuous_big_down'].fillna(False)
        & out['b1_volume_structure_ok'].fillna(False)
        & out['b1_j_low'].fillna(False)
        & out['b1_multicycle_proxy'].fillna(False)
        & out['b1_ma_zone_ok'].fillna(False)
    )

    out['b1_standard_proxy'] = (
        out['b1_drawdown_relaxed'].fillna(False)
        & out['b1_pullback_time_relaxed'].fillna(False)
        & out['b1_no_continuous_big_down'].fillna(False)
        & (
            out['b1_volume_structure_ok'].fillna(False)
            | out['b1_j_low'].fillna(False)
            | out['b1_ma_zone_ok'].fillna(False)
            | out['b1_multicycle_proxy'].fillna(False)
        )
    )
    return out
