import pandas as pd


def add_ma_features(df: pd.DataFrame, windows=(5, 10, 20)) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for w in windows:
        out[f'ma{w}'] = out['close'].rolling(w).mean()
    return out


def add_tactic_base_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    close = pd.to_numeric(out['close'], errors='coerce')
    low = pd.to_numeric(out['low'], errors='coerce')
    high = pd.to_numeric(out['high'], errors='coerce')

    out['white_line'] = close.ewm(span=10, adjust=False).mean().ewm(span=10, adjust=False).mean()
    ma14 = close.rolling(14).mean()
    ma28 = close.rolling(28).mean()
    ma57 = close.rolling(57).mean()
    ma114 = close.rolling(114).mean()
    out['yellow_line'] = (ma14 + ma28 + ma57 + ma114) / 4

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out['macd_dif'] = ema12 - ema26

    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()
    rsv = (close - low9) / (high9 - low9).replace(0, pd.NA) * 100
    out['kdj_k'] = rsv.ewm(alpha=1/3, adjust=False).mean()
    out['kdj_d'] = out['kdj_k'].ewm(alpha=1/3, adjust=False).mean()
    out['kdj_j'] = 3 * out['kdj_k'] - 2 * out['kdj_d']
    return out


def calc_support_pressure(df: pd.DataFrame, lookback: int = 10):
    if df.empty:
        return None, None
    tail = df.tail(lookback)
    support = float(tail['low'].min())
    pressure = float(tail['high'].max())
    return support, pressure
