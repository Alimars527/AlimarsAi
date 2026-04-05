from dataclasses import dataclass
import pandas as pd


@dataclass
class MarketRegimeResult:
    regime: str
    score: int
    summary: str


def evaluate_index(df: pd.DataFrame) -> MarketRegimeResult:
    if df.empty or len(df) < 2:
        return MarketRegimeResult('unknown', 0, '指数数据不足')

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    score = 0

    if latest['close'] > prev['close']:
        score += 1
    if latest['pct_chg'] > 1:
        score += 1
    if latest['vol'] > prev['vol']:
        score += 1
    if latest['pct_chg'] < -1:
        score -= 1

    if score >= 2:
        regime = 'strong'
    elif score <= -1:
        regime = 'weak'
    else:
        regime = 'neutral'

    summary = f"最新涨跌幅 {latest['pct_chg']:.2f}%，量能较前一日{'放大' if latest['vol'] > prev['vol'] else '缩小'}"
    return MarketRegimeResult(regime, score, summary)
