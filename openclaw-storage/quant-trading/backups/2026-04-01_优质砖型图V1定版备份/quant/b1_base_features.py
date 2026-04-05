import pandas as pd


def add_b1_base_features(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    close = pd.to_numeric(out.get('close'), errors='coerce')
    high = pd.to_numeric(out.get('high'), errors='coerce')
    low = pd.to_numeric(out.get('low'), errors='coerce')
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    recent_high_15 = high.rolling(15).max()
    drawdown = (recent_high_15 - close) / recent_high_15.replace(0, pd.NA)

    # 有效底座：回撤不能太深、结构未明显破坏、仍在中短期均线附近
    out['b1_base_drawdown_ok'] = (drawdown <= 0.18).fillna(False)
    out['b1_base_ma_hold'] = ((close >= ma20 * 0.97) | (close >= ma10 * 0.98)).fillna(False)
    out['b1_base_not_crash'] = (((close - low.rolling(5).min()) / close.replace(0, pd.NA)) > -0.12).fillna(False)
    out['b1_base_valid'] = (
        out['b1_base_drawdown_ok']
        & out['b1_base_ma_hold']
        & out['b1_base_not_crash']
    )
    return out
