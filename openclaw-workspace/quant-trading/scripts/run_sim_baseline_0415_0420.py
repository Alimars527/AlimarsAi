#!/usr/bin/env python3
"""
BaseLine模拟实盘: 2026-04-15 ~ 2026-04-20
完全复用 run_5w_combo_with_tpsl.py 的逻辑，仅改日期范围。
无任何人工干预，纯机械执行。
"""

from __future__ import annotations
import json, sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

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

START_DATE = "20230101"  # 需要完整历史来生成B1信号
END_DATE = "20260420"
INITIAL_CAPITAL = 50000.0
LOT_SIZE = 100
COMMISSION_RATE = 0.000086
MIN_COMMISSION = 5.0
STAMP_TAX_SELL = 0.0005
B1_MAX_HOLD_DAYS = 10
B1_TP1 = 0.10
B1_TP2 = 0.20
B1_YELLOW_SL = True
TRAILING_STOP_PCT = 0.07

# 只输出这个范围的交易
SIM_START = "20260415"

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

    print(f"[INFO] preparing universe: {len(meta)} codes")
    meta, code_data, code_idx, rotation_map = build_prepared_universe(
        START_DATE, END_DATE, DATA, min_rows=40,
    )
    print(f"[INFO] usable codes: {len(code_data)}")

    cash = INITIAL_CAPITAL
    positions: List[Position] = []
    trades = []
    nav_rows = []

    # 只处理4/15开始的交易日
    sim_cal = [td for td in cal if td >= SIM_START]
    print(f"[INFO] simulation dates: {sim_cal}")

    for td in sim_cal:
        # === 1) 平仓 ===
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
            yellow = safe_num(row.get("yellow_line"))

            is_b1 = p.strategy.startswith("B1")

            # 砖型图: 持1天收盘卖
            if not is_b1:
                if held < p.hold_days:
                    remain_positions.append(p)
                    continue
                sell_price = close
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name, "strategy": p.strategy,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4), "sell_price": round(sell_price, 4),
                    "shares": p.shares, "exit_reason": "hold_expire",
                    "pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.shares), 2),
                })
                continue

            # B1: TP2
            if not p.tp2_done and high >= p.buy_price * (1 + B1_TP2):
                sell_price = p.buy_price * (1 + B1_TP2)
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name, "strategy": p.strategy,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4), "sell_price": round(sell_price, 4),
                    "shares": p.shares, "exit_reason": "tp2",
                    "pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 2),
                })
                continue

            # TP1
            if not p.tp1_done and high >= p.buy_price * (1 + B1_TP1):
                sell_shares = p.shares // 2
                if sell_shares < LOT_SIZE:
                    sell_shares = p.shares
                sell_price = p.buy_price * (1 + B1_TP1)
                fee = _sell_fee(sell_price, sell_shares)
                proceeds = sell_price * sell_shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name, "strategy": p.strategy,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4), "sell_price": round(sell_price, 4),
                    "shares": sell_shares, "exit_reason": "tp1_partial",
                    "pnl": round(proceeds - p.buy_price * sell_shares - _buy_fee(p.buy_price, p.initial_shares), 2),
                })
                p.shares -= sell_shares
                p.tp1_done = True
                low = float(row["low"])
                p.trailing_stop_price = low * (1 - TRAILING_STOP_PCT)
                if p.shares <= 0:
                    continue

            # 回撤止损
            if p.tp1_done and p.trailing_stop_price > 0 and close <= p.trailing_stop_price:
                sell_price = close
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name, "strategy": p.strategy,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4), "sell_price": round(sell_price, 4),
                    "shares": p.shares, "exit_reason": "trailing_sl",
                    "pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 2),
                })
                continue

            # 黄线止损
            if B1_YELLOW_SL and pd.notna(yellow) and close < yellow:
                sell_price = close
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name, "strategy": p.strategy,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4), "sell_price": round(sell_price, 4),
                    "shares": p.shares, "exit_reason": "yellow_sl",
                    "pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 2),
                })
                continue

            # 最大持有期
            if held >= B1_MAX_HOLD_DAYS:
                sell_price = close
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name, "strategy": p.strategy,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4), "sell_price": round(sell_price, 4),
                    "shares": p.shares, "exit_reason": "max_hold",
                    "pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 2),
                })
                continue

            remain_positions.append(p)

        positions = remain_positions

        # === 2) 信号扫描 + 买入 ===
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

                if warn_overlap_only and not (b1 and brick):
                    continue
                if not (b1 or brick):
                    continue

                sigs.append({
                    "code": code, "name": r.name, "industry": r.industry,
                    "signal_date": td, "next_date": str(next_row["trade_date"]),
                    "signal_close": float(row["close"]),
                    "next_open": float(next_row["open"]),
                    "next_low": float(next_row["low"]),
                    "b1": b1, "brick": brick,
                    "j": float(safe_num(row.get("kdj_j"))) if pd.notna(safe_num(row.get("kdj_j"))) else 999,
                })

        # 排序+开仓
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

                # 纯B1前2日结构过滤
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

                slots_left = max(1, can_open - opened)
                budget = cash / slots_left
                avg5_prev = omav_avg5_map.get(s["signal_date"])

                if (s["b1"] and (not s["brick"])) or (s["b1"] and s["brick"]):
                    if avg5_prev is not None:
                        try:
                            avg5_v = float(avg5_prev)
                            if 1 < avg5_v <= 2 and not (s["b1"] and s["brick"]):
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
                    strategy=strategy, buy_date=s["next_date"], buy_price=buy_price,
                    shares=shares, hold_days=hold_days, initial_shares=shares,
                ))
                trades.append({
                    "code": s["code"], "name": s["name"], "strategy": strategy,
                    "buy_date": s["next_date"], "sell_date": None,
                    "buy_price": round(buy_price, 4), "sell_price": None,
                    "shares": shares, "exit_reason": "BUY",
                    "signal_date": td, "signal_close": s["signal_close"],
                    "next_open": s["next_open"], "next_low": s["next_low"],
                    "b1": s["b1"], "brick": s["brick"], "j": s["j"],
                })
                opened += 1

        # === 3) 记录NAV ===
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
            "holdings": "; ".join([f"{p.code} {p.name} {p.shares}股@{p.buy_price:.3f} [{p.strategy}]" for p in positions]),
        })

    # === 输出 ===
    print("\n" + "=" * 70)
    print("BaseLine模拟实盘 2026-04-15 ~ 2026-04-20 (纯机械执行)")
    print("=" * 70)

    # 买入交易
    buys = [t for t in trades if t["exit_reason"] == "BUY"]
    sells = [t for t in trades if t["exit_reason"] != "BUY"]

    print(f"\n【买入交易】({len(buys)}笔)")
    for t in buys:
        sig_type = "共振" if (t.get("b1") and t.get("brick")) else ("砖型图" if t.get("brick") else "B1")
        print(f"  {t['buy_date']} 买入 {t['code']} {t['name']} {t['shares']}股 @{t['buy_price']:.3f} [{sig_type}] J={t.get('j','?')}")

    print(f"\n【卖出交易】({len(sells)}笔)")
    for t in sells:
        print(f"  {t['sell_date']} 卖出 {t['code']} {t['name']} {t['shares']}股 @{t['sell_price']:.3f} [{t['exit_reason']}] PnL={t['pnl']:.2f}")

    print(f"\n【每日净值】")
    for r in nav_rows:
        print(f"  {r['trade_date']} 现金={r['cash']:.2f} 市值={r['market_value']:.2f} 总资产={r['total_equity']:.2f} 持仓数={r['positions']}")
        if r['holdings']:
            print(f"    持仓: {r['holdings']}")

    final = nav_rows[-1] if nav_rows else {}
    total_pnl = sum(t["pnl"] for t in sells if t.get("pnl"))
    total_return = (final.get("total_equity", INITIAL_CAPITAL) / INITIAL_CAPITAL - 1) * 100

    print(f"\n{'=' * 70}")
    print(f"总资产: {final.get('total_equity', 0):.2f}")
    print(f"现金: {final.get('cash', 0):.2f}")
    print(f"持仓市值: {final.get('market_value', 0):.2f}")
    print(f"总收益: {total_return:+.2f}%")
    print(f"已实现盈亏: {total_pnl:.2f}")
    if positions:
        print(f"剩余持仓: {len(positions)}只")
        for p in positions:
            print(f"  {p.code} {p.name} {p.shares}股 @{p.buy_price:.3f} [{p.strategy}] tp1={p.tp1_done} trailing={p.trailing_stop_price:.3f}")
    print(f"{'=' * 70}")

if __name__ == "__main__":
    main()
