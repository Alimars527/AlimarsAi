import pandas as pd


def compute_sector_rotation(daily_df: pd.DataFrame, stock_basic_df: pd.DataFrame, top_n: int = 8):
    if daily_df.empty or stock_basic_df.empty:
        return []
    merged = daily_df.merge(stock_basic_df[['ts_code', 'industry']], on='ts_code', how='left')
    merged = merged.dropna(subset=['industry'])
    stats = merged.groupby('industry').agg(
        avg_pct_chg=('pct_chg', 'mean'),
        win_count=('pct_chg', lambda s: int((s > 0).sum())),
        total_count=('pct_chg', 'count')
    )
    stats['win_rate'] = stats['win_count'] / stats['total_count']
    stats = stats.sort_values(['avg_pct_chg', 'win_rate'], ascending=False)
    result = []
    for industry, row in stats.head(top_n).iterrows():
        result.append({
            'industry': industry,
            'avg_pct_chg': round(float(row['avg_pct_chg']), 2),
            'win_rate': round(float(row['win_rate']) * 100, 1),
            'label': '主线偏强' if row['avg_pct_chg'] > 2 else ('活跃' if row['avg_pct_chg'] > 0.8 else '观察')
        })
    return result
