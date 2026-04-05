import pandas as pd


def infer_key_levels(df: pd.DataFrame):
    if df.empty or len(df) < 5:
        return None, None

    latest = df.iloc[-1]
    recent5 = df.tail(5)
    recent10 = df.tail(10)
    recent20 = df.tail(20) if len(df) >= 20 else df

    ma5 = recent5['close'].mean()
    ma10 = recent10['close'].mean()
    low5 = recent5['low'].min()
    low10 = recent10['low'].min()
    high5 = recent5['high'].max()
    high10 = recent10['high'].max()
    high20 = recent20['high'].max()

    # 支撑更偏近期交易区间，而不是过远低点
    support_candidates = [x for x in [ma5, ma10, low5, low10] if pd.notna(x)]
    pressure_candidates = [x for x in [high5, high10, high20] if pd.notna(x)]

    support = max([x for x in support_candidates if x <= latest['close']] or support_candidates)
    pressure = min([x for x in pressure_candidates if x >= latest['close']] or pressure_candidates)

    return float(support), float(pressure)
