import pandas as pd


def add_margin_features(price_df: pd.DataFrame, margin_df: pd.DataFrame) -> pd.DataFrame:
    if price_df is None or price_df.empty or margin_df is None or margin_df.empty:
        return price_df

    df = price_df.copy()
    mg = margin_df.copy()
    if 'trade_date' not in mg.columns:
        return df

    for col in ['rzye', 'rqye', 'rzmre', 'rqyl', 'rzche', 'rqchl', 'rqmcl', 'rzrqye']:
        if col in mg.columns:
            mg[col] = pd.to_numeric(mg[col], errors='coerce')

    keep_cols = ['trade_date'] + [c for c in ['rzye', 'rqye', 'rzmre', 'rqyl', 'rzche', 'rqchl', 'rqmcl', 'rzrqye'] if c in mg.columns]
    mg = mg[keep_cols].sort_values('trade_date').drop_duplicates(subset=['trade_date'], keep='last')

    df = df.merge(mg, on='trade_date', how='left')

    if 'rzye' in df.columns:
        df['margin_rzye_change'] = df['rzye'].diff()
        df['margin_rzye_change_5'] = df['rzye'].diff(5)
    if 'rqye' in df.columns:
        df['margin_rqye_change'] = df['rqye'].diff()
    if 'rzmre' in df.columns and 'rzche' in df.columns:
        df['margin_net_buy'] = df['rzmre'] - df['rzche']
        df['margin_net_buy_5'] = df['margin_net_buy'].rolling(5).sum()
        df['margin_positive_days_5'] = (df['margin_net_buy'] > 0).rolling(5).sum()
    if 'rqmcl' in df.columns and 'rqchl' in df.columns:
        df['short_net_change'] = df['rqmcl'] - df['rqchl']
    if 'rzrqye' in df.columns:
        df['margin_total_balance_change'] = df['rzrqye'].diff()

    return df
