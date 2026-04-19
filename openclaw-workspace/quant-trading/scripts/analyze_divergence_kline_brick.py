#!/usr/bin/env python3
"""
分析"K线绿但砖型图红"这种背离信号的统计特征
从BaseLine所有信号出发，按K线颜色×砖颜色分组统计后续收益
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quant.sim_replay_common import (
    build_prepared_universe,
    load_omav,
    load_trade_calendar,
    load_universe,
    safe_num,
)

DATA = ROOT / "data"
OUT = ROOT / "outputs"

START_DATE = "20230101"
END_DATE = "20260403"


def _sma_cn(series: pd.Series, n: int, m: int) -> pd.Series:
    x = safe_num(series).fillna(0.0)
    out = []
    prev = None
    for v in x.tolist():
        if prev is None:
            prev = v
        else:
            prev = (m * v + (n - m) * prev) / n
        out.append(prev)
    return pd.Series(out, index=series.index)


def b1_experimental_ok(df: pd.DataFrame, idx: int) -> bool:
    sub = df.iloc[: idx + 1].copy().reset_index(drop=True)
    if len(sub) < 160:
        return False
    C = safe_num(sub['close'])
    O = safe_num(sub['open'])
    H = safe_num(sub['high'])
    L = safe_num(sub['low'])
    VOL = safe_num(sub['vol']).fillna(0.0)
    REAL_YANG = (C > O) & ~(C < C.shift(1))
    REAL_YIN = (C < O) & ~(C > C.shift(1))
    ll9 = L.rolling(9).min(); hh9 = H.rolling(9).max()
    RSV = (C - ll9) / (hh9 - ll9) * 100
    K = _sma_cn(RSV, 3, 1)
    D = _sma_cn(K, 3, 1)
    J = 3 * K - 2 * D
    J_OK = J <= 13
    VOL_YANG1 = (VOL * REAL_YANG.astype(int)).rolling(57).sum()
    VOL_YIN1 = (VOL * REAL_YIN.astype(int)).rolling(57).sum()
    VOL_YANG2 = (VOL * REAL_YANG.astype(int)).rolling(14).sum()
    VOL_YIN2 = (VOL * REAL_YIN.astype(int)).rolling(14).sum()
    YANGYIN_OK1 = VOL_YANG1 > 1.25 * VOL_YIN1
    YANGYIN_OK2 = VOL_YANG2 > 2.25 * VOL_YIN2
    MV = safe_num(sub.get('total_mv_billion'))
    MVOK = MV >= 50
    O85 = O.rolling(21).min() + 0.95 * (O.rolling(21).max() - O.rolling(21).min())
    TOP15O = O >= O85
    FD15 = (C < C.shift(1)) & (C <= O) & (VOL >= 1.2 * VOL.shift(1))
    CNT28 = ((TOP15O & FD15).astype(int)).rolling(21).sum()
    GOOD28 = CNT28 <= 0
    AVG40 = VOL.rolling(40).mean()
    PLRY = (VOL > 1.95 * VOL.shift(1)) & (C > O) & (VOL > AVG40)
    PLRY_CNT = (((PLRY.astype(int)).rolling(14).sum() >= 2) | ((PLRY.astype(int)).rolling(57).sum() >= 4))
    prev_plry = PLRY.shift(1).eq(True)
    PLRY_FIRST = PLRY & (~prev_plry)
    PLRY_CONT = PLRY & prev_plry
    prev_real_yin = REAL_YIN.shift(1).eq(True)
    PRE_NOT_REALYIN = ~prev_real_yin
    HALF_DOWN = PRE_NOT_REALYIN & (C < C.shift(1)) & (VOL <= 0.5 * VOL.shift(1))
    CNT_FIRST = PLRY_FIRST.astype(int).rolling(57).sum()
    CNT_CONT = PLRY_CONT.astype(int).rolling(57).sum()
    CNT_HALF = HALF_DOWN.astype(int).rolling(57).sum()
    THREE_SUM_OK = (CNT_FIRST + CNT_CONT + CNT_HALF) >= 4
    MAXVOL28 = VOL.rolling(28).max()
    MAX28_BAD = (VOL == MAXVOL28) & REAL_YIN
    MAX28_OK = MAX28_BAD.astype(int).rolling(28).sum() == 0
    A1 = ((PLRY_CNT & YANGYIN_OK1 & J_OK & MVOK & GOOD28 & THREE_SUM_OK & MAX28_OK) | (PLRY_CNT & YANGYIN_OK2 & J_OK & MVOK & GOOD28 & MAX28_OK))
    HMSHORTWL = sub['white_line']
    HMLONGYL = sub['yellow_line']
    B1 = (HMSHORTWL >= HMLONGYL * 0.985) & (C >= HMLONGYL * 0.985) & A1
    return bool(B1.iloc[-1])


def main():
    omav = load_omav(DATA)
    omav_map = omav.set_index("trade_date").to_dict("index")
    cal = load_trade_calendar(START_DATE, END_DATE, DATA)
    cal_set = set(cal)

    meta = load_universe(DATA)
    print(f"[INFO] preparing universe: {len(meta)}")
    meta, code_data, code_idx, rotation_map = build_prepared_universe(
        START_DATE, END_DATE, DATA, min_rows=40,
    )
    print(f"[INFO] usable codes: {len(code_data)}")

    # 收集所有信号的K线颜色和砖颜色
    all_signals = []  # 每条: {date, code, k_color, brick_color, strategy, next_pnl_1d, next_pnl_5d}

    for td_idx, td in enumerate(cal):
        om = omav_map.get(td, {})
        bear = str(om.get("omav_bear_regime_flag", "False")).lower() == "true"
        warn = str(om.get("omav_rotation_warning_flag", "False")).lower() == "true"

        for r in meta.itertuples(index=False):
            code = r.ts_code
            if code not in code_data:
                continue
            idx_map = code_idx[code]
            if td not in idx_map:
                continue
            idx = idx_map[td]
            df = code_data[code]
            if idx < 25 or idx + 5 >= len(df):
                continue

            row = df.iloc[idx]
            next_row = df.iloc[idx + 1]
            if str(next_row["trade_date"]) not in cal_set:
                continue

            # 信号检测
            b1 = b1_experimental_ok(df, idx)
            brick_v1 = bool(row.get("brick_raw_turn_red", False)) and bool(row.get("brick_history_ok", False))
            brick = False
            if brick_v1 and (not bear) and (not warn) and idx >= 4:
                z = safe_num(df["brick_formula_value"]).fillna(0)
                g = df["brick_formula_green"].fillna(False).astype(bool)
                white = safe_num(row.get("white_line"))
                yellow = safe_num(row.get("yellow_line"))
                high_b = safe_num(row.get("high"))
                rotation_ok = rotation_map.get((td, r.industry), False)
                brick = bool(
                    rotation_ok and pd.notna(white) and pd.notna(yellow) and pd.notna(high_b)
                    and high_b >= white and white > yellow
                    and g.iloc[idx - 1] and g.iloc[idx - 2] and g.iloc[idx - 3] and g.iloc[idx - 4]
                    and z.iloc[idx - 4] > z.iloc[idx - 3] > z.iloc[idx - 2] > z.iloc[idx - 1]
                    and z.iloc[idx] >= z.iloc[idx - 1]
                )

            if not (b1 or brick):
                continue

            # K线颜色: close<open=绿(阴), close>=open=红(阳)
            close = safe_num(row["close"])
            open_px = safe_num(row["open"])
            k_is_green = close < open_px  # K线绿

            # 砖型图砖颜色
            brick_is_red = bool(row.get("brick_raw_turn_red", False))  # 砖红

            # 后续收益
            next_open = safe_num(next_row["open"])
            next_close_1d = safe_num(df.iloc[idx + 1]["close"])
            # 找5个交易日后的收盘价
            future_idx = min(idx + 5, len(df) - 1)
            next_close_5d = safe_num(df.iloc[future_idx]["close"])

            if pd.isna(next_open) or next_open == 0:
                continue

            pnl_1d = (next_close_1d / next_open - 1) * 100 if next_open > 0 else 0
            pnl_5d = (next_close_5d / next_open - 1) * 100 if next_open > 0 else 0

            # 确定策略类型
            if b1 and brick:
                strategy = "BOTH"
            elif brick:
                strategy = "BRICK"
            else:
                strategy = "B1"

            all_signals.append({
                "date": td,
                "code": code,
                "name": r.name,
                "industry": r.industry,
                "strategy": strategy,
                "k_green": k_is_green,
                "brick_red": brick_is_red,
                "pct_chg": float(safe_num(row.get("pct_chg", 0))),
                "next_pnl_1d": float(pnl_1d),
                "next_pnl_5d": float(pnl_5d),
            })

        if (td_idx + 1) % 100 == 0:
            print(f"  processed {td_idx+1}/{len(cal)} ({td})")

    df_sig = pd.DataFrame(all_signals)
    print(f"\n总信号数: {len(df_sig)}")

    # 分组统计: K线颜色 × 砖颜色
    print("\n" + "=" * 70)
    print("全信号统计: K线颜色 × 砖颜色")
    print("=" * 70)

    df_sig["group"] = df_sig.apply(
        lambda r: f"K{'绿' if r['k_green'] else '红'}_砖{'红' if r['brick_red'] else '绿'}",
        axis=1
    )

    for grp_name, grp in df_sig.groupby("group"):
        n = len(grp)
        wr_1d = (grp["next_pnl_1d"] > 0).mean() * 100
        wr_5d = (grp["next_pnl_5d"] > 0).mean() * 100
        avg_1d = grp["next_pnl_1d"].mean()
        avg_5d = grp["next_pnl_5d"].mean()
        med_1d = grp["next_pnl_1d"].median()
        print(f"\n  {grp_name} ({n}条):")
        print(f"    次日: 均收益{avg_1d:+.2f}%, 中位{med_1d:+.2f}%, 胜率{wr_1d:.1f}%")
        print(f"    5日: 均收益{avg_5d:+.2f}%, 胜率{wr_5d:.1f}%")

    # 按策略分组再看
    print("\n" + "=" * 70)
    print("按策略分组: K绿+砖红 vs 其他")
    print("=" * 70)

    df_sig["is_divergence"] = df_sig["k_green"] & df_sig["brick_red"]  # K绿+砖红=背离

    for strat in ["BRICK", "B1", "BOTH"]:
        sub = df_sig[df_sig["strategy"] == strat]
        if len(sub) == 0:
            continue
        print(f"\n  [{strat}] 共{len(sub)}条信号:")
        for is_div, grp in sub.groupby("is_divergence"):
            label = "K绿+砖红(背离)" if is_div else "其他"
            n = len(grp)
            wr_1d = (grp["next_pnl_1d"] > 0).mean() * 100
            avg_1d = grp["next_pnl_1d"].mean()
            avg_5d = grp["next_pnl_5d"].mean()
            print(f"    {label}: {n}条, 次日均收益{avg_1d:+.2f}%, 5日均{avg_5d:+.2f}%, 次日胜率{wr_1d:.1f}%")

    # 特殊关注：砖型图策略中的背离
    print("\n" + "=" * 70)
    print("核心关注：砖型图策略(BRICK+BOTH)中 K绿+砖红 的详细")
    print("=" * 70)

    brick_signals = df_sig[df_sig["strategy"].isin(["BRICK", "BOTH"])]
    div_signals = brick_signals[brick_signals["is_divergence"]]
    non_div_signals = brick_signals[~brick_signals["is_divergence"]]

    print(f"\n  砖型图信号总数: {len(brick_signals)}")
    print(f"  K绿+砖红(背离): {len(div_signals)} ({len(div_signals)/len(brick_signals)*100:.1f}%)")
    print(f"  其他: {len(non_div_signals)}")

    if len(div_signals) > 0:
        print(f"\n  背离信号表现:")
        print(f"    次日均收益: {div_signals['next_pnl_1d'].mean():+.2f}%")
        print(f"    次日中位收益: {div_signals['next_pnl_1d'].median():+.2f}%")
        print(f"    次日胜率: {(div_signals['next_pnl_1d']>0).mean()*100:.1f}%")
        print(f"    5日均收益: {div_signals['next_pnl_5d'].mean():+.2f}%")
        print(f"    5日胜率: {(div_signals['next_pnl_5d']>0).mean()*100:.1f}%")

        print(f"\n  非背离信号表现:")
        print(f"    次日均收益: {non_div_signals['next_pnl_1d'].mean():+.2f}%")
        print(f"    次日中位收益: {non_div_signals['next_pnl_1d'].median():+.2f}%")
        print(f"    次日胜率: {(non_div_signals['next_pnl_1d']>0).mean()*100:.1f}%")
        print(f"    5日均收益: {non_div_signals['next_pnl_5d'].mean():+.2f}%")
        print(f"    5日胜率: {(non_div_signals['next_pnl_5d']>0).mean()*100:.1f}%")

        # pct_chg分布
        print(f"\n  背离信号pct_chg分布:")
        print(f"    均值: {div_signals['pct_chg'].mean():+.2f}%")
        print(f"    中位: {div_signals['pct_chg'].median():+.2f}%")
        print(f"    范围: [{div_signals['pct_chg'].min():+.2f}%, {div_signals['pct_chg'].max():+.2f}%]")

    # 保存详细数据
    df_sig.to_csv(OUT / "divergence_analysis_kline_brick.csv", index=False, encoding="utf-8-sig")
    print(f"\n详细数据已保存: outputs/divergence_analysis_kline_brick.csv")


if __name__ == "__main__":
    main()
