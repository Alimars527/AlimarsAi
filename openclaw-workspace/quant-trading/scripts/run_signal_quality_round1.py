#!/usr/bin/env python3
"""
信号质量分层 — 第一轮：单维度 pct_chg 过滤
在 BaseLine 基础上，仅增加买入日涨幅(pct_chg)过滤条件
控制变量：卖出/止盈止损/资金管理全部不变

实验:
- 1A: pct_chg >= -2%
- 1B: pct_chg >= -1%
- 1C: pct_chg >= 0%
"""

from __future__ import annotations
import json
import sys
import time
from dataclasses import dataclass
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
    prepare_code_df,
    safe_num,
)

DATA = ROOT / "data"
OUT = ROOT / "outputs"

START_DATE = "20230101"
END_DATE = "20260403"
INITIAL_CAPITAL = 50000.0
LOT_SIZE = 100
COMMISSION_RATE = 0.000086
MIN_COMMISSION = 5.0
STAMP_TAX_SELL = 0.0005
B1_MAX_HOLD_DAYS = 10
B1_TP1 = 0.10
B1_TP2 = 0.20
B1_YELLOW_SL = True


@dataclass
class Position:
    code: str
    name: str
    industry: str
    strategy: str
    buy_date: str
    buy_price: float
    shares: int
    hold_days: int
    initial_shares: int = 0
    tp1_done: bool = False
    tp2_done: bool = False
    trailing_stop_price: float = 0.0


def _commission(amount: float) -> float:
    return max(amount * COMMISSION_RATE, MIN_COMMISSION)


def _buy_fee(price: float, shares: int) -> float:
    return _commission(price * shares)


def _sell_fee(price: float, shares: int) -> float:
    amount = price * shares
    return _commission(amount) + amount * STAMP_TAX_SELL


def j_threshold(td: str) -> float:
    y = td[:4]
    if y == "2023": return -10
    if y == "2024": return 0
    if y == "2025": return 18
    return 25


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


def run_single(pct_threshold: float, tag: str, meta, code_data, code_idx, rotation_map,
               omav_map, omav_avg5_map, cal, cal_set):
    """跑单个实验"""
    print(f"\n{'='*60}")
    print(f"[{tag}] pct_chg >= {pct_threshold}%")
    print(f"{'='*60}")

    cash = INITIAL_CAPITAL
    positions: List[Position] = []
    trades = []
    nav_rows = []
    tp1_count = tp2_count = trailing_sl_count = yellow_sl_count = maxhold_count = 0

    for td_idx, td in enumerate(cal):
        # 1) 平仓
        remain_positions = []
        for p in positions:
            idx_map = code_idx.get(p.code, {})
            if td not in idx_map:
                remain_positions.append(p)
                continue
            idx = idx_map[td]
            df = code_data[p.code]
            buy_idx = idx_map.get(p.buy_date)
            if buy_idx is None:
                remain_positions.append(p)
                continue
            held = idx - buy_idx
            row = df.iloc[idx]
            high = float(row["high"])
            close = float(row["close"])
            open_px = float(row["open"])
            yellow = safe_num(row.get("yellow_line"))

            is_b1 = p.strategy.startswith("B1")

            if not is_b1:
                if held < p.hold_days:
                    remain_positions.append(p)
                    continue
                sell_price = close
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name, "industry": p.industry,
                    "strategy": p.strategy,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4),
                    "sell_price": round(sell_price, 4),
                    "shares": p.shares,
                    "gross_pnl": round((sell_price - p.buy_price) * p.shares, 4),
                    "fees": round(_buy_fee(p.buy_price, p.shares) + fee, 4),
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.shares), 4),
                    "exit_reason": "hold_expire",
                })
                continue

            # B1 止盈止损
            if not p.tp2_done and high >= p.buy_price * (1 + B1_TP2):
                sell_price = p.buy_price * (1 + B1_TP2)
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name, "industry": p.industry,
                    "strategy": p.strategy,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4),
                    "sell_price": round(sell_price, 4),
                    "shares": p.shares,
                    "gross_pnl": round((sell_price - p.buy_price) * p.shares, 4),
                    "fees": round(_buy_fee(p.buy_price, p.initial_shares) + fee, 4),
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "exit_reason": "tp2",
                })
                tp2_count += 1
                continue

            if not p.tp1_done and high >= p.buy_price * (1 + B1_TP1):
                sell_shares = p.shares // 2
                if sell_shares < LOT_SIZE:
                    sell_shares = p.shares
                sell_price = p.buy_price * (1 + B1_TP1)
                fee = _sell_fee(sell_price, sell_shares)
                proceeds = sell_price * sell_shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name, "industry": p.industry,
                    "strategy": p.strategy,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4),
                    "sell_price": round(sell_price, 4),
                    "shares": sell_shares,
                    "gross_pnl": round((sell_price - p.buy_price) * sell_shares, 4),
                    "fees": round(_buy_fee(p.buy_price, p.initial_shares) + fee, 4),
                    "net_pnl": round(proceeds - p.buy_price * sell_shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "exit_reason": "tp1_partial",
                })
                tp1_count += 1
                p.shares -= sell_shares
                p.tp1_done = True
                low = float(row["low"])
                p.trailing_stop_price = low * (1 - 0.07)
                if p.shares <= 0:
                    continue

            if p.tp1_done and p.trailing_stop_price > 0 and close <= p.trailing_stop_price:
                sell_price = close
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name, "industry": p.industry,
                    "strategy": p.strategy,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4),
                    "sell_price": round(sell_price, 4),
                    "shares": p.shares,
                    "gross_pnl": round((sell_price - p.buy_price) * p.shares, 4),
                    "fees": round(_buy_fee(p.buy_price, p.initial_shares) + fee, 4),
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "exit_reason": "trailing_sl",
                })
                trailing_sl_count += 1
                continue

            if B1_YELLOW_SL and pd.notna(yellow) and close < yellow:
                sell_price = close
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name, "industry": p.industry,
                    "strategy": p.strategy,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4),
                    "sell_price": round(sell_price, 4),
                    "shares": p.shares,
                    "gross_pnl": round((sell_price - p.buy_price) * p.shares, 4),
                    "fees": round(_buy_fee(p.buy_price, p.initial_shares) + fee, 4),
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "exit_reason": "yellow_sl",
                })
                yellow_sl_count += 1
                continue

            if held >= B1_MAX_HOLD_DAYS:
                sell_price = close
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name, "industry": p.industry,
                    "strategy": p.strategy,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4),
                    "sell_price": round(sell_price, 4),
                    "shares": p.shares,
                    "gross_pnl": round((sell_price - p.buy_price) * p.shares, 4),
                    "fees": round(_buy_fee(p.buy_price, p.initial_shares) + fee, 4),
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "exit_reason": "max_hold",
                })
                maxhold_count += 1
                continue

            remain_positions.append(p)

        positions = remain_positions

        # 2) 生成信号
        om = omav_map.get(td, {})
        bear = str(om.get("omav_bear_regime_flag", "False")).lower() == "true"
        warn = str(om.get("omav_rotation_warning_flag", "False")).lower() == "true"
        max_new = 0 if bear else (1 if warn else 3)
        max_total_pos = 1 if warn else 3
        free_slots = max(0, max_total_pos - len(positions))
        can_open = min(max_new, free_slots)
        warn_overlap_only = bool(warn and not bear)

        sigs = []
        if can_open > 0:
            for r in meta.itertuples(index=False):
                code = r.ts_code
                if code not in code_data:
                    continue
                idx_map = code_idx[code]
                if td not in idx_map:
                    continue
                idx = idx_map[td]
                df = code_data[code]
                if idx < 25 or idx + 1 >= len(df):
                    continue

                row = df.iloc[idx]
                next_row = df.iloc[idx + 1]
                if str(next_row["trade_date"]) not in cal_set:
                    continue

                # === 唯一修改：pct_chg 过滤 ===
                pct_chg = safe_num(row.get("pct_chg"))
                if pd.isna(pct_chg) or pct_chg < pct_threshold:
                    continue
                # === END ===

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
                        rotation_ok
                        and pd.notna(white)
                        and pd.notna(yellow)
                        and pd.notna(high_b)
                        and high_b >= white
                        and white > yellow
                        and g.iloc[idx - 1]
                        and g.iloc[idx - 2]
                        and g.iloc[idx - 3]
                        and g.iloc[idx - 4]
                        and z.iloc[idx - 4] > z.iloc[idx - 3] > z.iloc[idx - 2] > z.iloc[idx - 1]
                        and z.iloc[idx] >= z.iloc[idx - 1]
                    )

                if warn_overlap_only and not (b1 and brick):
                    continue
                if not (b1 or brick):
                    continue

                sigs.append({
                    "code": code, "name": r.name, "industry": r.industry,
                    "signal_date": td,
                    "next_date": str(next_row["trade_date"]),
                    "signal_close": float(row["close"]),
                    "next_open": float(next_row["open"]),
                    "next_low": float(next_row["low"]),
                    "b1": b1, "brick": brick,
                    "j": float(safe_num(row.get("kdj_j"))) if pd.notna(safe_num(row.get("kdj_j"))) else 999,
                })

        # 3) 排序 + 开仓
        if can_open > 0 and sigs:
            def _rank(s):
                p = 0 if (s["b1"] and s["brick"]) else (1 if s["brick"] else 2)
                return (p, s["j"])

            sigs = sorted(sigs, key=_rank)
            selected = sigs[: can_open * 2]

            opened = 0
            for s in selected:
                if opened >= can_open:
                    break

                if s["b1"] and s["brick"]:
                    strategy = "B1_EXPERIMENTAL+BRICK_V3"
                    buy_price = min(s["signal_close"] * 0.993, s["next_open"] * 0.988)
                    hold_days = 1
                elif s["brick"]:
                    strategy = "BRICK_V3"
                    buy_price = min(s["signal_close"] * 0.995, s["next_open"] * 0.99)
                    hold_days = 1
                else:
                    strategy = "B1_EXPERIMENTAL"
                    buy_price = min(s["signal_close"] * 0.993, s["next_open"] * 0.988)
                    hold_days = B1_MAX_HOLD_DAYS

                if s["next_low"] > buy_price:
                    continue

                slots_left = max(1, can_open - opened)
                budget = cash / slots_left
                avg5_prev = omav_avg5_map.get(s["signal_date"])

                if s["b1"] and (not s["brick"]):
                    try:
                        signal_idx = code_idx[s["code"]][s["signal_date"]]
                        signal_df = code_data[s["code"]]
                        prev1_pct = float(signal_df.iloc[signal_idx - 1].get("pct_chg", 0.0)) if signal_idx >= 1 else 0.0
                        prev2_pct = float(signal_df.iloc[signal_idx - 2].get("pct_chg", 0.0)) if signal_idx >= 2 else 0.0
                    except Exception:
                        prev1_pct = 0.0
                        prev2_pct = 0.0
                    if (prev1_pct <= -1.5) and (prev2_pct <= -1.5):
                        continue

                if (s["b1"] and (not s["brick"])) or (s["b1"] and s["brick"]):
                    if avg5_prev is not None:
                        try:
                            avg5_prev = float(avg5_prev)
                            if 1 < avg5_prev <= 2 and not (s["b1"] and s["brick"]):
                                budget *= 0.5
                        except Exception:
                            pass

                shares = int(budget // buy_price // LOT_SIZE) * LOT_SIZE
                if shares <= 0:
                    continue

                fee = _buy_fee(buy_price, shares)
                cost = buy_price * shares + fee
                if cost > cash:
                    continue

                cash -= cost
                positions.append(Position(
                    code=s["code"], name=s["name"], industry=s["industry"],
                    strategy=strategy,
                    buy_date=s["next_date"], buy_price=buy_price,
                    shares=shares, hold_days=hold_days,
                    initial_shares=shares,
                ))
                opened += 1

        # 4) 净值
        mv = 0.0
        for p in positions:
            idx_map = code_idx.get(p.code, {})
            if td in idx_map:
                px = float(code_data[p.code].iloc[idx_map[td]]["close"])
                mv += px * p.shares
            else:
                mv += p.buy_price * p.shares

        nav_rows.append({
            "trade_date": td,
            "cash": round(cash, 2),
            "market_value": round(mv, 2),
            "total_equity": round(cash + mv, 2),
            "positions": len(positions),
        })

        if (td_idx + 1) % 50 == 0:
            print(f"  [{tag}] {td_idx+1}/{len(cal)} ({td})")

    # 统计
    nav = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)

    final_equity = float(nav.iloc[-1]["total_equity"]) if not nav.empty else INITIAL_CAPITAL
    total_return = (final_equity / INITIAL_CAPITAL - 1) * 100

    eq = nav["total_equity"].values
    peak = np.maximum.accumulate(eq)
    drawdown = (eq - peak) / peak * 100
    max_dd = float(drawdown.min())

    years = (pd.Timestamp(END_DATE) - pd.Timestamp(START_DATE)).days / 365.25
    cagr = ((final_equity / INITIAL_CAPITAL) ** (1 / years) - 1) * 100 if years > 0 else 0

    exit_stats = {}
    if not trades_df.empty:
        exit_stats = trades_df.groupby("exit_reason").agg(
            count=("exit_reason", "size"),
            avg_pnl=("net_pnl", "mean"),
            total_pnl=("net_pnl", "sum"),
            win_rate=("net_pnl", lambda x: (x > 0).mean() * 100),
        ).to_dict(orient="index")

    yearly = {}
    if not trades_df.empty:
        trades_df["sell_year"] = trades_df["sell_date"].str[:4]
        for yr, grp in trades_df.groupby("sell_year"):
            yearly[yr] = {
                "count": int(len(grp)),
                "win_rate": round(float((grp["net_pnl"] > 0).mean() * 100), 2),
                "total_pnl": round(float(grp["net_pnl"].sum()), 2),
            }

    summary = {
        "version": tag,
        "pct_threshold": pct_threshold,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "trade_count": int(len(trades_df)),
        "win_rate_pct": round(float((trades_df["net_pnl"] > 0).mean() * 100), 2) if not trades_df.empty else 0.0,
        "cagr_pct": round(cagr, 2),
        "exit_stats": exit_stats,
        "tp_sl_counts": {
            "tp1_partial": tp1_count,
            "tp2_full": tp2_count,
            "trailing_sl": trailing_sl_count,
            "yellow_sl": yellow_sl_count,
            "max_hold": maxhold_count,
        },
        "yearly_breakdown": yearly,
        "baseline_ref": "+219.99% / 585笔 / WR50.6% / DD-16.16% / CAGR 42.99%",
    }

    nav.to_csv(OUT / f"sim_replay_20230101_{tag}_nav.csv", index=False, encoding="utf-8-sig")
    trades_df.to_csv(OUT / f"sim_replay_20230101_{tag}_trades.csv", index=False, encoding="utf-8-sig")
    (OUT / f"sim_replay_20230101_{tag}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n[{tag}] 结果: +{total_return:.2f}% / {len(trades_df)}笔 / WR{summary['win_rate_pct']:.1f}% / DD{max_dd:.2f}% / CAGR{cagr:.2f}%")
    return summary


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    omav = load_omav(DATA)
    omav_map = omav.set_index("trade_date").to_dict("index")
    omav_avg5_map = {}
    if "trade_date" in omav.columns:
        om2 = omav.copy().sort_values("trade_date").reset_index(drop=True)
        val_col = "omav" if "omav" in om2.columns else ("omav_value" if "omav_value" in om2.columns else None)
        if val_col is not None:
            om2[val_col] = safe_num(om2[val_col])
            om2["avg5_prev"] = om2[val_col].shift(1).rolling(5).mean()
            omav_avg5_map = om2.set_index("trade_date")["avg5_prev"].to_dict()
    cal = load_trade_calendar(START_DATE, END_DATE, DATA)
    cal_set = set(cal)

    meta = load_universe(DATA)
    print(f"[INFO] preparing universe: {len(meta)}")
    meta, code_data, code_idx, rotation_map = build_prepared_universe(
        START_DATE, END_DATE, DATA, min_rows=40,
    )
    print(f"[INFO] usable codes: {len(code_data)}")

    experiments = [
        (-2.0, "sq_pct_ge_neg2"),
        (-1.0, "sq_pct_ge_neg1"),
        (0.0,  "sq_pct_ge_0"),
    ]

    results = []
    t0 = time.time()
    for pct_thresh, tag in experiments:
        t1 = time.time()
        s = run_single(pct_thresh, tag, meta, code_data, code_idx, rotation_map,
                       omav_map, omav_avg5_map, cal, cal_set)
        s["elapsed_sec"] = round(time.time() - t1, 1)
        results.append(s)

    total_time = round(time.time() - t0, 1)

    # 对比表
    print("\n" + "=" * 70)
    print("第一轮对比 (BaseLine: +219.99% / 585笔 / WR50.6% / DD-16.16%)")
    print("=" * 70)
    for s in results:
        print(f"  {s['version']:20s}: +{s['total_return_pct']:7.2f}% / {s['trade_count']:3d}笔 / "
              f"WR{s['win_rate_pct']:.1f}% / DD{s['max_drawdown_pct']:.2f}% / CAGR{s['cagr_pct']:.1f}% "
              f"[{s['elapsed_sec']}s]")
    print(f"\n总耗时: {total_time}s")


if __name__ == "__main__":
    main()
