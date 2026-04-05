import pandas as pd


def add_b1b2_structure_features(df: pd.DataFrame) -> pd.DataFrame:
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

    # 平台压缩：近5日高低点区间不大，且不是深杀
    platform_range = (prev_high_5 - prev_low_5) / prev_high_5.replace(0, pd.NA)
    out['platform_tight_5'] = (platform_range <= 0.12).fillna(False)

    # 平台后再启动：接近或突破前5/10日平台高点
    out['restart_near_break_5'] = (close >= prev_high_5 * 0.995).fillna(False)
    out['restart_near_break_10'] = (close >= prev_high_10 * 0.99).fillna(False)

    # 二次强化：不是孤立大长阴后反抽，而是收盘强、上影不过长
    body = (close - open_).abs()
    full_range = (high - low).replace(0, pd.NA)
    upper_shadow = (high - close.where(close >= open_, open_)).clip(lower=0)
    out['restart_body_ok'] = ((body / full_range) >= 0.3).fillna(False)
    out['restart_upper_shadow_ok'] = ((upper_shadow / full_range) <= 0.35).fillna(False)

    # 放量强化但不过热：较前一日放量，且不是极端爆量
    prev_vol = vol.shift(1).replace(0, pd.NA)
    vol_ratio = vol / prev_vol
    out['restart_volume_ok'] = ((vol_ratio >= 1.1) & (vol_ratio <= 2.5)).fillna(False)

    # 综合结构：平台后再启动 / 二次强化 代理
    out['b1b2_platform_restart'] = (
        out['platform_tight_5']
        & (out['restart_near_break_5'] | out['restart_near_break_10'])
        & out['restart_body_ok']
        & out['restart_upper_shadow_ok']
        & out['restart_volume_ok']
    )
    return out
