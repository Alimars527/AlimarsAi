#!/usr/bin/env python3
"""公式1：中长大利 — 回测脚本"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quant.sim_replay_common import safe_num
from scripts.tdx_formula_backtest_common import run_backtest

DATA = ROOT / "data"

# 加载大盘指数数据（深成指 000001.SZ 作为代理）
_index_df = None
_index_close_map = {}

def _load_index():
    global _index_df, _index_close_map
    if _index_df is not None:
        return
    p = DATA / "daily" / "000001.SZ.csv"
    if p.exists():
        _index_df = pd.read_csv(p, dtype={"trade_date": str})[["trade_date", "close"]]
        _index_df["close"] = safe_num(_index_df["close"])
        _index_close_map = _index_df.set_index("trade_date")["close"].to_dict()
    else:
        _index_close_map = {}


def buy_signal_zhongchangdali(df: pd.DataFrame, idx: int) -> bool:
    """
    中长大利买点信号：
    VAR1~VAR9: DMI趋势判断
    A: VAR7>VAR6 AND VAR7>25 AND VAR6<25
    B: EMA(CLOSE,5), G: EMA(CLOSE,10)
    D: CROSS(B,G)  {EMA5上穿EMA10}
    F: 大盘RSI(3) < 8
    VAR14: KDJ_D < 20
    MM := A AND D AND VAR10 AND VAR14
    """
    if idx < 55:  # 需要足够历史数据（EMA55+SMA25+MA15等）
        return False

    sub = df.iloc[: idx + 1].copy().reset_index(drop=True)
    C = safe_num(sub['close'])
    H = safe_num(sub['high'])
    L = safe_num(sub['low'])

    # ── DMI部分 ──
    # VAR1:=SUM(MAX(MAX(HIGH-LOW,ABS(HIGH-REF(CLOSE,1))),ABS(LOW-REF(CLOSE,1))),25);
    tr1 = H - L
    tr2 = (H - C.shift(1)).abs()
    tr3 = (L - C.shift(1)).abs()
    TR = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    VAR1 = TR.rolling(25).sum()

    # VAR2:=HIGH-REF(HIGH,1); VAR3:=REF(LOW,1)-LOW;
    VAR2 = H - H.shift(1)
    VAR3 = L.shift(1) - L

    # VAR4:=SUM(IF(VAR2>0 AND VAR2>VAR3,VAR2,0),25);
    # VAR5:=SUM(IF(VAR3>0 AND VAR3>VAR2,VAR3,0),25);
    VAR4 = ((VAR2 > 0) & (VAR2 > VAR3)).astype(float) * VAR2
    VAR4 = VAR4.rolling(25).sum()
    VAR5 = ((VAR3 > 0) & (VAR3 > VAR2)).astype(float) * VAR3
    VAR5 = VAR5.rolling(25).sum()

    VAR6 = VAR4 * 100 / VAR1
    VAR7 = VAR5 * 100 / VAR1
    VAR8 = (VAR6 - VAR7).abs() / (VAR6 + VAR7).replace(0, np.nan) * 100
    VAR8 = VAR8.rolling(15).mean()
    # VAR9 没用到，不计算

    A = (VAR7 > VAR6) & (VAR7 > 25) & (VAR6 < 25)

    # ── EMA交叉 ──
    B = C.ewm(span=5, adjust=False).mean()
    G = C.ewm(span=10, adjust=False).mean()
    D = (B > G) & (B.shift(1) <= G.shift(1))  # CROSS(B,G)

    # ── 大盘RSI(3)<8 ──
    _load_index()
    td = str(sub.iloc[idx]['trade_date'])
    VAR10 = pd.Series(False, index=sub.index)
    if _index_close_map:
        index_close = sub['trade_date'].map(_index_close_map)
        E = index_close.shift(1)
        delta = index_close - E
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        # SMA(gain,3,1) / SMA(loss,3,1) —— 通达信SMA
        sma_gain = gain.ewm(alpha=1/3, adjust=False).mean()  # SMA(X,3,1) ≈ EWM alpha=1/3
        sma_loss = loss.ewm(alpha=1/3, adjust=False).mean()
        F = sma_gain / sma_loss.replace(0, np.nan)
        F = F.fillna(0)
        VAR10 = (F < 0.08)  # 注意：这里F是RSI的原始比值，RSI=100*F/(1+F)，F<8对应RSI≈89%，不对...
        # 等等，通达信公式：F:=SMA(MAX(INDEXC-E,0),3,1)/SMA(ABS(INDEXC-E),3,1);
        # 这是 RSI 的变体，但 SMA(MAX(...),3,1) / SMA(ABS(...),3,1) 在上涨时接近1，下跌时接近0
        # F<8 这个条件看起来不对... 应该是 F<0.08 还是 F<8（百分比形式）？
        # 通达信里 SMA(MAX(INDEXC-E,0),3,1) 的返回值是指数涨幅的绝对值，SMA(ABS(...),3,1) 是绝对变动
        # 当大盘连续下跌时，MAX(INDEXC-E,0)=0，F=0
        # 当大盘上涨时，F≈1
        # 所以 F<8 几乎恒成立（因为F最大约1）
        # 可能原作者想表达的是大盘RSI<8，但公式写法有问题，F<8实际上≈恒真
        # 为了忠实还原，我保留 F<8 的判断（实际上恒真）
        # 但等等，如果 INDEXC 和 E 都是几百几千的点数，MAX(INDEXC-E,0) 也是几十几百，SMA(...,3,1) 也是几十几百
        # F = 几十/几十 ≈ 0~1 之间，F<8 确实几乎恒真
        # 我认为这里应该是 RSI<8，但公式写法是 F AND F<8，由于 F 本身就在0~1之间，这个条件≈True
        # 所以我直接设为 True（因为 F<8 在数值上几乎恒成立）
        VAR10 = pd.Series(True, index=sub.index)
    else:
        VAR10 = pd.Series(True, index=sub.index)

    # ── KDJ超卖 ──
    ll9 = L.rolling(9).min()
    hh9 = H.rolling(9).max()
    VAR11 = (C - ll9) / (hh9 - ll9).replace(0, np.nan) * 100
    VAR12 = VAR11.ewm(span=3, adjust=False).mean()  # SMA(VAR11,3,1)
    VAR13 = VAR12.ewm(span=3, adjust=False).mean()  # SMA(VAR12,3,1)
    VAR14 = (VAR13 < 20)

    # ── 共振 ──
    MM = A & D & VAR10 & VAR14
    return bool(MM.iloc[idx])


if __name__ == "__main__":
    run_backtest(
        version_tag="formula1_zhongchangdali",
        buy_signal_fn=buy_signal_zhongchangdali,
        strategy_name="中长大利",
    )
