import pandas as pd


def add_b1_pattern_features(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    close = pd.to_numeric(out['close'], errors='coerce')
    open_ = pd.to_numeric(out['open'], errors='coerce')
    vol = pd.to_numeric(out['vol'], errors='coerce')

    # 放量上涨 / 缩量下跌
    out['up_day'] = close > open_
    out['down_day'] = close < open_
    out['vol_up'] = vol > vol.shift(1)
    out['vol_down'] = vol < vol.shift(1)
    out['b1_rise_on_volume'] = out['up_day'] & out['vol_up']
    out['b1_pullback_on_shrink'] = out['down_day'] & out['vol_down']

    # 连续缩量洗盘
    out['shrink_2'] = (vol < vol.shift(1)) & (vol.shift(1) < vol.shift(2))
    out['shrink_3'] = (vol < vol.shift(1)) & (vol.shift(1) < vol.shift(2)) & (vol.shift(2) < vol.shift(3))
    out['b1_extreme_shrink'] = out['shrink_2'] | out['shrink_3']

    # 白线/黄线附近修复
    if 'white_line' in out.columns and 'yellow_line' in out.columns:
        white = pd.to_numeric(out['white_line'], errors='coerce')
        yellow = pd.to_numeric(out['yellow_line'], errors='coerce')
        out['b1_white_not_broken'] = close >= white * 0.985
        out['b1_from_yellow_zone'] = (close >= yellow * 0.98) & (close <= yellow * 1.03)
    else:
        out['b1_white_not_broken'] = False
        out['b1_from_yellow_zone'] = False

    # 阶梯回踩：近几日低点逐步抬高/不恶化（简化版）
    low = pd.to_numeric(out['low'], errors='coerce') if 'low' in out.columns else close
    out['b1_step_pullback'] = (low >= low.shift(1) * 0.97) & (low.shift(1) >= low.shift(2) * 0.97)

    return out
