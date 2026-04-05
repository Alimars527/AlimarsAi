import pandas as pd


def add_brick_flags(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    high = pd.to_numeric(out['high'], errors='coerce')
    low = pd.to_numeric(out['low'], errors='coerce')
    close = pd.to_numeric(out['close'], errors='coerce')
    vol = pd.to_numeric(out.get('vol'), errors='coerce')
    ma5 = pd.to_numeric(out.get('ma5'), errors='coerce') if 'ma5' in out.columns else close.rolling(5).mean()
    ma10 = pd.to_numeric(out.get('ma10'), errors='coerce') if 'ma10' in out.columns else close.rolling(10).mean()
    white = pd.to_numeric(out.get('white_line'), errors='coerce') if 'white_line' in out.columns else close
    yellow = pd.to_numeric(out.get('yellow_line'), errors='coerce') if 'yellow_line' in out.columns else close
    pct = pd.to_numeric(out.get('pct_chg'), errors='coerce') if 'pct_chg' in out.columns else pd.Series(index=out.index, dtype='float64')

    rolling_high = high.rolling(4).max()
    rolling_low = low.rolling(4).min()
    spread = (rolling_high - rolling_low).replace(0, float('nan'))

    var1a = ((rolling_high - close) / spread) * 100 - 90
    var1a = pd.to_numeric(var1a, errors='coerce')
    var2a = var1a.ewm(alpha=1/4, adjust=False).mean() + 100
    var3a = ((close - rolling_low) / spread) * 100
    var3a = pd.to_numeric(var3a, errors='coerce')
    var4a = var3a.ewm(alpha=1/6, adjust=False).mean()
    var5a = var4a.ewm(alpha=1/6, adjust=False).mean() + 100
    brick = pd.to_numeric(var5a - var2a - 4, errors='coerce').clip(lower=0)

    out['brick_value'] = brick
    out['brick_red_turn_raw'] = (brick.shift(1) < brick).fillna(False)
    out['brick_green_turn'] = (brick.shift(1) > brick).fillna(False)

    streaks = []
    streak = 0
    for flag in out['brick_green_turn'].tolist():
        if flag:
            streak += 1
        else:
            streak = 0
        streaks.append(streak)
    out['brick_green_streak'] = pd.Series(streaks, index=out.index, dtype='int64')

    vol_ok = vol >= (vol.rolling(5).mean() * 0.9)
    trend_ok = (ma5 >= ma10) | (close >= ma5)
    yellow_ok = close >= yellow * 0.98
    white_ok = close >= white * 0.97
    crash_filter = pct > -3
    green_stage_ok = out['brick_green_streak'].shift(1).fillna(0) >= 4
    white_stage_ok = (low.rolling(4).min() >= (white.rolling(4).min() * 0.99)).fillna(False)

    out['brick_red_turn'] = (
        out['brick_red_turn_raw']
        & green_stage_ok
        & white_stage_ok
        & vol_ok.fillna(False)
        & trend_ok.fillna(False)
        & yellow_ok.fillna(False)
        & white_ok.fillna(False)
        & crash_filter.fillna(False)
    )
    out['brick_exec_ready'] = (
        (brick.shift(1) <= brick).fillna(False)
        & (brick > 0).fillna(False)
        & green_stage_ok
        & white_stage_ok
        & vol_ok.fillna(False)
        & trend_ok.fillna(False)
        & yellow_ok.fillna(False)
        & white_ok.fillna(False)
        & crash_filter.fillna(False)
    )
    return out
