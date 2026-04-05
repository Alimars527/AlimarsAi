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
    vol = pd.to_numeric(out.get('vol'), errors='coerce')

    hhv4 = high.rolling(4).max()
    llv4 = low.rolling(4).min()
    spread = (hhv4 - llv4).replace(0, float('nan'))

    var1a = (hhv4 - close) / spread * 100 - 90
    var2a = tdx_sma(var1a, 4, 1) + 100
    var3a = (close - llv4) / spread * 100
    var4a = tdx_sma(var3a, 6, 1)
    var5a = tdx_sma(var4a, 6, 1) + 100
    var6a = var5a - var2a
    brick = pd.to_numeric(var6a.where(var6a > 4, 0) - 4, errors='coerce').clip(lower=0)

    prev_brick = brick.shift(1).fillna(0)
    aa = prev_brick < brick
    cc = (aa.shift(1).fillna(False) == False) & aa

    prev_green_height = prev_brick.where(prev_brick > brick, prev_brick)
    brick_height_ok = brick >= (prev_green_height * 2.0 / 3.0).fillna(0)

    body = (close - open_).abs()
    full_range = (high - low).replace(0, float('nan'))
    small_body = (body / full_range) < 0.35
    volume_boost = vol >= (vol.rolling(5).mean() * 1.2)

    out['brick_formula_value'] = brick
    out['brick_formula_red'] = aa.fillna(False)
    out['brick_formula_green'] = (prev_brick > brick).fillna(False)
    out['brick_formula_turn_red'] = cc.fillna(False)
    out['brick_formula_height_ok'] = brick_height_ok.fillna(False)
    out['brick_formula_volume_boost'] = (small_body.fillna(False) & volume_boost.fillna(False))
    out['brick_formula_signal'] = (
        out['brick_formula_turn_red']
        & out['brick_formula_height_ok']
    )
    out['brick_formula_strong_signal'] = (
        out['brick_formula_signal']
        & out['brick_formula_volume_boost']
    )
    return out
