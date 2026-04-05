import pandas as pd


def add_hkhold_features(price_df: pd.DataFrame, hkhold_df: pd.DataFrame) -> pd.DataFrame:
    if price_df is None or price_df.empty or hkhold_df is None or hkhold_df.empty:
        return price_df

    df = price_df.copy()
    hk = hkhold_df.copy()

    if 'trade_date' not in hk.columns:
        return df

    for col in ['vol', 'ratio']:
        if col in hk.columns:
            hk[col] = pd.to_numeric(hk[col], errors='coerce')

    keep_cols = ['trade_date']
    if 'vol' in hk.columns:
        keep_cols.append('vol')
    if 'ratio' in hk.columns:
        keep_cols.append('ratio')
    hk = hk[keep_cols].sort_values('trade_date').drop_duplicates(subset=['trade_date'], keep='last')
    hk = hk.rename(columns={'vol': 'hkhold_vol', 'ratio': 'hkhold_ratio'})

    df = df.merge(hk, on='trade_date', how='left')
    if 'hkhold_vol' in df.columns:
        df['hkhold_vol'] = pd.to_numeric(df['hkhold_vol'], errors='coerce')
        df['hkhold_vol_change'] = df['hkhold_vol'].diff()
        df['hkhold_vol_ma5'] = df['hkhold_vol'].rolling(5).mean()
    if 'hkhold_ratio' in df.columns:
        df['hkhold_ratio'] = pd.to_numeric(df['hkhold_ratio'], errors='coerce')
        df['hkhold_ratio_change'] = df['hkhold_ratio'].diff()
        df['hkhold_ratio_ma5'] = df['hkhold_ratio'].rolling(5).mean()
        df['hkhold_ratio_ma10'] = df['hkhold_ratio'].rolling(10).mean()
        df['hkhold_ratio_trend_up'] = (df['hkhold_ratio_ma5'] > df['hkhold_ratio_ma10']).fillna(False)
        df['hkhold_ratio_positive_5'] = (df['hkhold_ratio_change'] > 0).rolling(5).sum()
    return df
