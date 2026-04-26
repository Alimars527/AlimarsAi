#!/usr/bin/env python3
"""公式2：金峰暴利 — 回测脚本"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quant.sim_replay_common import safe_num
from scripts.tdx_formula_backtest_common import run_backtest


def _tdx_filter(series: pd.Series, n: int) -> pd.Series:
    """模拟通达信 FILTER(X,N)：X首次为真后，N周期内屏蔽重复信号"""
    result = pd.Series(False, index=series.index)
    last_true = -n - 1
    for i in range(len(series)):
        if series.iloc[i] and (i - last_true) > n:
            result.iloc[i] = True
            last_true = i
    return result


def buy_signal_jinfengbaoli(df: pd.DataFrame, idx: int) -> bool:
    """
    金峰暴利买点信号：
    V6:=CLOSE/REF(CLOSE,3)>=1.1;
    买入:IF(FILTER(V6, 3), 30, 0)
    """
    if idx < 3:
        return False
    sub = df.iloc[: idx + 1].copy().reset_index(drop=True)
    C = safe_num(sub['close'])
    V6 = C / C.shift(3) >= 1.10
    BUY = _tdx_filter(V6, 3)
    return bool(BUY.iloc[idx])


if __name__ == "__main__":
    run_backtest(
        version_tag="formula2_jinfengbaoli",
        buy_signal_fn=buy_signal_jinfengbaoli,
        strategy_name="金峰暴利",
    )
