"""
Candlestick Pattern Detection Library — 12 Bullish Patterns

Groups:
  A组(单蜡烛线): 锤子线(含蜻蜓十字强版), 倒锤子线, 光头光脚阳线
  B组(双蜡烛线): 看涨吞没, 刺透形态, 看涨孕线(含十字孕线强版)
  C组(多蜡烛线): 启明星(含十字启明星强版), 三白兵, 上升三法

Usage:
    from quant.candlestick_patterns import add_candlestick_patterns
    df = add_candlestick_patterns(df)
    # df now has pat_* boolean columns
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── Thresholds ───────────────────────────────────────────
_SMALL_SHADOW = 0.10   # "small shadow" = shadow/range < 10%
_MIN_BODY     = 0.01   # meaningful body = body/close >= 1%
_LARGE_BODY   = 0.02   # "large body"   = body/close >= 2%
_MARUBOZU_TOL = 0.015  # marubozu shadow tolerance (yuan)

ALL_PATTERN_COLS = [
    "pat_hammer", "pat_dragonfly_doji", "pat_inverted_hammer",
    "pat_bullish_marubozu", "pat_bullish_engulfing", "pat_piercing_line",
    "pat_bullish_harami", "pat_harami_cross",
    "pat_morning_star", "pat_morning_doji_star",
    "pat_three_white_soldiers", "pat_rising_three_methods",
]

GROUP_COLS = [
    "pat_hammer_group", "pat_harami_group", "pat_morning_star_group",
]

# 9 categories → which columns to combine
PATTERN_GROUPS = {
    "锤子线":       ["pat_hammer", "pat_dragonfly_doji"],
    "倒锤子线":     ["pat_inverted_hammer"],
    "光头光脚阳线": ["pat_bullish_marubozu"],
    "看涨吞没":     ["pat_bullish_engulfing"],
    "刺透形态":     ["pat_piercing_line"],
    "看涨孕线":     ["pat_bullish_harami", "pat_harami_cross"],
    "启明星":       ["pat_morning_star", "pat_morning_doji_star"],
    "三白兵":       ["pat_three_white_soldiers"],
    "上升三法":     ["pat_rising_three_methods"],
}


def _s(arr: np.ndarray, n: int, fill: float = np.nan) -> np.ndarray:
    """Shift array right by n positions."""
    out = np.empty_like(arr, dtype=float)
    out[:n] = fill
    if n < len(arr):
        out[n:] = arr[:-n]
    return out


def add_candlestick_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Add boolean pattern columns to an OHLC DataFrame.

    Required columns: open, high, low, close  (sorted by trade_date asc).
    Adds 12 individual + 3 group boolean columns.
    """
    df = df.copy()
    n = len(df)
    if n < 15:
        for c in ALL_PATTERN_COLS + GROUP_COLS:
            df[c] = False
        return df

    # ── Basic measures ──
    o = df["open"].values.astype(float)
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)
    c = df["close"].values.astype(float)

    body   = np.abs(c - o)
    upper  = h - np.maximum(o, c)
    lower  = np.minimum(o, c) - l
    rng    = h - l
    c_safe = np.where(c > 0, c, 1e-10)
    r_safe = np.where(rng > 0, rng, 1e-10)

    is_bull = c > o
    is_bear = c < o
    body_f  = body / c_safe
    upper_f = upper / r_safe
    lower_f = lower / r_safe

    # MA10 for downtrend context
    ma10 = pd.Series(c).rolling(10, min_periods=5).mean().values
    downtrend = c < ma10

    # ── Shifted arrays ──
    o1 = _s(o, 1); h1 = _s(h, 1); l1 = _s(l, 1); c1 = _s(c, 1)
    o2 = _s(o, 2); c2 = _s(c, 2)
    o3 = _s(o, 3); h3 = _s(h, 3); l3 = _s(l, 3)
    o4 = _s(o, 4); c4 = _s(c, 4); h4 = _s(h, 4); l4 = _s(l, 4)

    bear1 = _s(is_bear.astype(float), 1, 0).astype(bool)
    bear2 = _s(is_bear.astype(float), 2, 0).astype(bool)
    bull_s1 = _s(is_bull.astype(float), 1, 0).astype(bool)
    bull_s2 = _s(is_bull.astype(float), 2, 0).astype(bool)
    bull_s3 = _s(is_bull.astype(float), 3, 0).astype(bool)
    bull_s4 = _s(is_bull.astype(float), 4, 0).astype(bool)

    body1 = _s(body, 1, 0); body2 = _s(body, 2, 0)
    body_f1 = _s(body_f, 1, 0); body_f2 = _s(body_f, 2, 0)
    body_f3 = _s(body_f, 3, 0); body_f4 = _s(body_f, 4, 0)
    upper_f1 = _s(upper_f, 1, 1.0)

    # Shifted highs/lows for rising-3-method
    h_s1 = _s(h, 1); h_s2 = _s(h, 2); h_s3 = _s(h, 3)
    l_s1 = _s(l, 1); l_s2 = _s(l, 2); l_s3 = _s(l, 3)

    # ── 1. 锤子线 Hammer ──────────────────────────────────
    df["pat_hammer"] = (
        (body > 0)
        & (lower >= 2 * body)
        & (upper <= _SMALL_SHADOW * rng)
        & downtrend
    )

    # ── 2. 蜻蜓十字 Dragonfly Doji (强版锤子线) ──────────
    df["pat_dragonfly_doji"] = (
        (np.abs(c - o) <= 0.1 * rng)
        & (upper <= _SMALL_SHADOW * rng)
        & (lower >= 0.6 * rng)
        & downtrend
    )

    # ── 3. 倒锤子线 Inverted Hammer ──────────────────────
    df["pat_inverted_hammer"] = (
        (body > 0)
        & (upper >= 2 * body)
        & (lower <= _SMALL_SHADOW * rng)
        & downtrend
    )

    # ── 4. 光头光脚阳线 Bullish Marubozu ─────────────────
    df["pat_bullish_marubozu"] = (
        is_bull
        & (upper < _MARUBOZU_TOL)
        & (lower < _MARUBOZU_TOL)
        & (body_f >= _LARGE_BODY)
    )

    # ── 5. 看涨吞没 Bullish Engulfing ────────────────────
    engulf = (
        bear1 & is_bull
        & (o <= c1)
        & (c >= o1)
    )
    engulf[:1] = False
    df["pat_bullish_engulfing"] = engulf

    # ── 6. 刺透形态 Piercing Line ────────────────────────
    mid_prev = (o1 + c1) / 2
    pierce = (
        bear1 & is_bull
        & (o < l1)
        & (c > mid_prev)
        & (c < o1)
    )
    pierce[:1] = False
    df["pat_piercing_line"] = pierce

    # ── 7. 看涨孕线 Bullish Harami ───────────────────────
    harami = (
        bear1 & is_bull
        & (o >= c1)
        & (c <= o1)
        & (body < body1 * 0.5)
    )
    harami[:1] = False
    df["pat_bullish_harami"] = harami

    # ── 8. 十字孕线 Harami Cross (强版) ──────────────────
    df["pat_harami_cross"] = harami & (np.abs(c - o) <= 0.1 * rng)

    # ── 9. 启明星 Morning Star ───────────────────────────
    c2_small = body1 <= 0.3 * body2
    c2_gap   = h1 < c2
    c3_into  = c > (o2 + c2) / 2
    mstar = (
        bear2 & (body_f2 >= _LARGE_BODY)
        & c2_small & c2_gap
        & is_bull & c3_into
    )
    mstar[:2] = False
    df["pat_morning_star"] = mstar

    # ── 10. 十字启明星 Morning Doji Star (强版) ──────────
    c2_doji = np.abs(c1 - o1) <= 0.1 * (h1 - l1 + 1e-10)
    df["pat_morning_doji_star"] = mstar & c2_doji

    # ── 11. 三白兵 Three White Soldiers ──────────────────
    progressive = (c1 > c2) & (c > c1)
    open_in_prev = (o1 >= o2) & (o1 <= c2) & (o >= o1) & (o <= c1)
    short_us = (upper_f1 <= 0.4) & (_s(upper_f, 2, 1.0) <= 0.4) & (upper_f <= 0.4)
    decent = (body_f2 >= _MIN_BODY) & (body_f1 >= _MIN_BODY) & (body_f >= _MIN_BODY)
    soldiers = bull_s2 & bull_s1 & is_bull & progressive & open_in_prev & short_us & decent
    soldiers[:2] = False
    df["pat_three_white_soldiers"] = soldiers

    # ── 12. 上升三法 Rising Three Methods ────────────────
    c1_big_bull = bull_s4 & (body_f4 >= _LARGE_BODY)
    inner_ok = (
        (h_s3 <= h4) & (l_s3 >= l4)    # C2 in C1 range
        & (h_s2 <= h4) & (l_s2 >= l4)  # C3 in C1 range
        & (h_s1 <= h4) & (l_s1 >= l4)  # C4 in C1 range
        & ~(bull_s3 & (body_f3 >= _LARGE_BODY))
        & ~(bull_s2 & (body_f2 >= _LARGE_BODY))
        & ~(bull_s1 & (body_f1 >= _LARGE_BODY))
    )
    c5_new_high = is_bull & (c > c4)
    rising3 = c1_big_bull & inner_ok & c5_new_high
    rising3[:4] = False
    df["pat_rising_three_methods"] = rising3

    # ── Group columns (OR of sub-patterns) ──
    df["pat_hammer_group"]      = df["pat_hammer"] | df["pat_dragonfly_doji"]
    df["pat_harami_group"]      = df["pat_bullish_harami"] | df["pat_harami_cross"]
    df["pat_morning_star_group"] = df["pat_morning_star"] | df["pat_morning_doji_star"]

    return df
