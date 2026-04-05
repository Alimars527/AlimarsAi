"""第二阶段：基础绩效指标（第一版）"""

import pandas as pd


def summarize_returns(df: pd.DataFrame, return_col: str = 'return_pct') -> dict:
    if df is None or df.empty or return_col not in df.columns:
        return {
            'count': 0,
            'win_rate': None,
            'avg_return': None,
            'avg_win': None,
            'avg_loss': None,
        }

    series = df[return_col].dropna()
    if series.empty:
        return {
            'count': 0,
            'win_rate': None,
            'avg_return': None,
            'avg_win': None,
            'avg_loss': None,
        }

    wins = series[series > 0]
    losses = series[series <= 0]

    return {
        'count': int(series.shape[0]),
        'win_rate': round(float((series > 0).mean()), 4),
        'avg_return': round(float(series.mean()), 4),
        'avg_win': round(float(wins.mean()), 4) if not wins.empty else 0.0,
        'avg_loss': round(float(losses.mean()), 4) if not losses.empty else 0.0,
    }
