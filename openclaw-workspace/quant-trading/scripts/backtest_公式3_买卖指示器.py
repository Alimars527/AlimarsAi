#!/usr/bin/env python3
"""公式3：买卖指示器 — 回测脚本"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quant.sim_replay_common import safe_num
from scripts.tdx_formula_backtest_common import run_backtest


def _slope(series: pd.Series, n: int) -> pd.Series:
    """计算N周期线性回归斜率（类似通达信SLOPE）"""
    arr = series.values
    slopes = np.full(len(arr), np.nan)
    x = np.arange(n, dtype=float)
    for i in range(n - 1, len(arr)):
        y = arr[i - n + 1:i + 1]
        if np.all(np.isnan(y)):
            continue
        mask = ~np.isnan(y)
        if mask.sum() < 2:
            continue
        # 用最小二乘拟合
        xm = x[mask]
        ym = y[mask]
        s = np.polyfit(xm, ym, 1)[0]
        slopes[i] = s
    return pd.Series(slopes, index=series.index)


def _tdx_filter(series: pd.Series, n: int) -> pd.Series:
    """模拟通达信 FILTER(X,N)"""
    result = pd.Series(False, index=series.index)
    last_true = -n - 1
    for i in range(len(series)):
        if series.iloc[i] and (i - last_true) > n:
            result.iloc[i] = True
            last_true = i
    return result


def buy_signal_maimaizhishiqi(df: pd.DataFrame, idx: int) -> bool:
    """
    买卖指示器买点信号（任一买点触发）：
    买1: CROSS(K,D) AND K<安全线
    买2: CROSS(K,安全线)
    买3: CROSS(K,D) AND K>安全线
    买4: FILTER(V6, 3)  {3日涨10%}
    最佳买入: K>REF(K,1) AND REF(K,1)<REF(K,2) AND K<安全线*1.05
    """
    if idx < 60:  # EMA55 + SLOPE7
        return False

    sub = df.iloc[: idx + 1].copy().reset_index(drop=True)
    C = safe_num(sub['close'])
    H = safe_num(sub['high'])
    L = safe_num(sub['low'])
    O = safe_num(sub['open'])

    # VAR1:=(2*CLOSE+HIGH+LOW+OPEN)/5;
    VAR1 = (2 * C + H + L + O) / 5

    # 安全线: EMA(VAR1,55)
    安全线 = VAR1.ewm(span=55, adjust=False).mean()

    # K: SLOPE(EMA(VAR1,2),7)*15+VAR1
    ema_var1_2 = VAR1.ewm(span=2, adjust=False).mean()
    slope_val = _slope(ema_var1_2, 7)
    K = slope_val * 15 + VAR1

    # D: EMA(K,2)
    D = K.ewm(span=2, adjust=False).mean()

    # J: 2.8*K-1.8*D (J未参与买卖逻辑，不计算)

    # 买1: CROSS(K,D) AND K<安全线
    cross_kd = (K > D) & (K.shift(1) <= D.shift(1))
    买1 = cross_kd & (K < 安全线)

    # 买2: CROSS(K,安全线)
    cross_k_safe = (K > 安全线) & (K.shift(1) <= 安全线.shift(1))
    买2 = cross_k_safe

    # 买3: CROSS(K,D) AND K>安全线
    买3 = cross_kd & (K > 安全线)

    # 买4: FILTER(V6, 3)
    V6 = C / C.shift(3) >= 1.10
    买4 = _tdx_filter(V6, 3)

    # 最佳买入: K>REF(K,1) AND REF(K,1)<REF(K,2) AND K<安全线*1.05
    VAR_TURN_BUY = (K > K.shift(1)) & (K.shift(1) < K.shift(2)) & (K < 安全线 * 1.05)
    最佳买入 = VAR_TURN_BUY

    # 任一个买点触发
    买点 = 买1 | 买2 | 买3 | 买4 | 最佳买入
    return bool(买点.iloc[idx])


if __name__ == "__main__":
    run_backtest(
        version_tag="formula3_maimaizhishiqi",
        buy_signal_fn=buy_signal_maimaizhishiqi,
        strategy_name="买卖指示器",
    )
