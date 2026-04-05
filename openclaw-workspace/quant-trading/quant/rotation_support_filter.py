import pandas as pd


def add_rotation_support_filter(df: pd.DataFrame, industry_day_strength: pd.DataFrame = None, industry: str = None) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    out = df.copy()
    if 'industry' not in out.columns:
        out['industry'] = industry if industry is not None else ''
    if industry_day_strength is None or industry_day_strength.empty:
        out['rotation_support'] = False
        out['rotation_support_level'] = 'none'
        return out

    rot = industry_day_strength.copy()
    if 'trade_date' in rot.columns:
        rot['trade_date'] = pd.to_datetime(rot['trade_date'])
    keep_cols = [c for c in ['trade_date', 'industry', 'rotation_support', 'rotation_support_level'] if c in rot.columns]
    rot = rot[keep_cols].drop_duplicates(subset=['trade_date', 'industry'], keep='last')

    if 'trade_date' in out.columns:
        out['trade_date'] = pd.to_datetime(out['trade_date'])
    out = out.merge(rot, on=['trade_date', 'industry'], how='left')
    out['rotation_support'] = out.get('rotation_support', False).fillna(False)
    out['rotation_support_level'] = out.get('rotation_support_level', 'none').fillna('none')
    return out


def build_rotation_support_proxy(sample_df: pd.DataFrame) -> pd.DataFrame:
    if sample_df is None or sample_df.empty:
        return pd.DataFrame(columns=['trade_date', 'industry', 'rotation_support', 'rotation_support_level'])

    df = sample_df.copy()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['next_day_return'] = pd.to_numeric(df['next_day_return'], errors='coerce')
    grp = df.groupby(['trade_date', 'industry']).agg(
        sample_count=('code', 'count'),
        day_avg_return=('next_day_return', 'mean'),
    ).reset_index().sort_values(['industry', 'trade_date'])
    grp['avg3'] = grp.groupby('industry')['day_avg_return'].transform(lambda s: s.rolling(3, min_periods=1).mean())
    grp['count3'] = grp.groupby('industry')['sample_count'].transform(lambda s: s.rolling(3, min_periods=1).mean())
    grp['rotation_support'] = (grp['avg3'] > 0) & (grp['count3'] >= 1)
    grp['rotation_support_level'] = 'none'
    grp.loc[grp['rotation_support'], 'rotation_support_level'] = 'support'
    grp.loc[(grp['avg3'] > 0.5) & (grp['count3'] >= 1.5), 'rotation_support_level'] = 'strong'
    return grp[['trade_date', 'industry', 'rotation_support', 'rotation_support_level']]
