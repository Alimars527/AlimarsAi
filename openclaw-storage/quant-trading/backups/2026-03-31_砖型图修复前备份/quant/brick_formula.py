import pandas as pd


def tdx_sma(series: pd.Series, n: int, m: int = 1) -> pd.Series:
    s = pd.to_numeric(series, errors='coerce').copy()
    if s.empty:
        return s
    out = []
    prev = None
    for x in s.tolist():
        if pd.isna(x):
            out.append(float(prev) if prev is not None and not pd.isna(prev) else float('nan'))
            continue
        if prev is None or pd.isna(prev):
            prev = float(x)
        else:
            prev = float((m * float(x) + (n - m) * float(prev)) / n)
        out.append(float(prev))
    return pd.Series(out, index=s.index, dtype='float64')


def add_brick_formula_flags(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    high = pd.to_numeric(out['high'], errors='coerce')
    low = pd.to_numeric(out['low'], errors='coerce')
    close = pd.to_numeric(out['close'], errors='coerce')
    open_ = pd.to_numeric(out.get('open'), errors='coerce')
    white = pd.to_numeric(out.get('white_line'), errors='coerce') if 'white_line' in out.columns else close

    hhv4 = high.rolling(4).max()
    llv4 = low.rolling(4).min()
    spread = (hhv4 - llv4).replace(0, float('nan'))

    var1a = (hhv4 - close) / spread * 100 - 90
    var2a = tdx_sma(var1a, 4, 1) + 100
    var3a = (close - llv4) / spread * 100
    var4a = tdx_sma(var3a, 6, 1)
    var5a = tdx_sma(var4a, 6, 1) + 100
    var6a = var5a - var2a
    brick = pd.to_numeric(var6a.where(var6a > 4, 0) - 4, errors='coerce').clip(lower=0).fillna(0)

    prev_brick = brick.shift(1).fillna(0)
    prev2_brick = brick.shift(2).fillna(0)
    aa = (prev_brick < brick).fillna(False)
    bb = (prev_brick > brick).fillna(False)
    cc = ((~aa.shift(1).fillna(False)) & aa).fillna(False)

    green = bb
    streaks = []
    streak = 0
    for flag in green.tolist():
        if flag:
            streak += 1
        else:
            streak = 0
        streaks.append(streak)
    green_streak = pd.Series(streaks, index=out.index, dtype='int64')
    green_streak_prev = green_streak.shift(1).fillna(0)

    body_low = pd.concat([open_, close], axis=1).min(axis=1)
    body_high = pd.concat([open_, close], axis=1).max(axis=1)
    full_range = (high - low).replace(0, float('nan'))
    body = (close - open_).abs()

    # 基础层：只认原始公式绿转红
    out['brick_formula_value'] = brick
    out['brick_formula_red'] = aa
    out['brick_formula_green'] = bb
    out['brick_formula_turn_red'] = cc
    out['brick_raw_turn_red'] = cc

    # A组：结构强化层
    out['brick_green_streak'] = green_streak
    out['brick_a1_height_ok'] = ((prev_brick > 0) & (brick >= prev_brick)).fillna(False)
    out['brick_a2_green_streak_ok'] = (green_streak_prev >= 4)
    out['brick_a3_white_body_ok'] = (body_high >= white * 0.99).fillna(False)
    out['brick_a_group_ok'] = (
        out['brick_raw_turn_red']
        & out['brick_a1_height_ok']
        & out['brick_a2_green_streak_ok']
        & out['brick_a3_white_body_ok']
    )

    # B组：砖大柱小
    brick_large = (brick >= brick.rolling(5, min_periods=1).max() * 0.9).fillna(False)
    small_body = ((body / full_range) < 0.35).fillna(False)
    out['brick_b1_big_brick_small_candle'] = brick_large & small_body
    out['brick_b_group_ok'] = out['brick_b1_big_brick_small_candle']

    # C组：走势质量 + 共振增强
    rolling5_high = close.rolling(5, min_periods=1).max()
    out['brick_c1_shallow_pullback_ok'] = ((close / rolling5_high - 1) >= -0.12).fillna(False)
    out['brick_c2_with_b1'] = pd.to_numeric(out.get('b1_strength', pd.Series(0, index=out.index, dtype='float64')), errors='coerce').fillna(0) >= 3
    out['brick_c2_with_b2'] = out.get('b2_signal', pd.Series(False, index=out.index)).fillna(False)
    out['brick_c_group_ok'] = out['brick_c1_shallow_pullback_ok']

    # 兼容旧输出：基础层信号不再混入叠加层
    out['brick_formula_signal'] = out['brick_raw_turn_red']
    out['brick_formula_strong_signal'] = out['brick_a_group_ok'] & out['brick_b_group_ok']
    return out
