import pandas as pd


def add_moneyflow_features(df: pd.DataFrame, moneyflow_df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    if moneyflow_df is None or moneyflow_df.empty:
        out['net_mf_amount'] = 0.0
        out['mf_amount_3'] = 0.0
        out['mf_amount_5'] = 0.0
        out['mf_amount_10'] = 0.0
        out['mf_positive_days_5'] = 0.0
        out['mf_strength'] = 0.0
        out['mf_divergence'] = False
        return out

    mf = moneyflow_df.copy()
    for col in ['net_mf_amount']:
        if col in mf.columns:
            mf[col] = pd.to_numeric(mf[col], errors='coerce')
    mf = mf[['trade_date', 'net_mf_amount']].copy()
    out = out.merge(mf, on='trade_date', how='left')
    out['net_mf_amount'] = pd.to_numeric(out['net_mf_amount'], errors='coerce').fillna(0.0)
    out['mf_amount_3'] = out['net_mf_amount'].rolling(3).sum().fillna(0.0)
    out['mf_amount_5'] = out['net_mf_amount'].rolling(5).sum().fillna(0.0)
    out['mf_amount_10'] = out['net_mf_amount'].rolling(10).sum().fillna(0.0)
    out['mf_positive_flag'] = (out['net_mf_amount'] > 0).astype(float)
    out['mf_positive_days_5'] = out['mf_positive_flag'].rolling(5).sum().fillna(0.0)
    close_amount = pd.to_numeric(out['close'], errors='coerce') * pd.to_numeric(out.get('vol', 0), errors='coerce')
    close_amount = close_amount.replace(0, pd.NA)
    out['mf_strength'] = (out['mf_amount_5'] / close_amount).fillna(0.0)
    out['mf_divergence'] = (pd.to_numeric(out.get('pct_chg', 0), errors='coerce') > 0) & (out['mf_amount_5'] < 0)
    return out
