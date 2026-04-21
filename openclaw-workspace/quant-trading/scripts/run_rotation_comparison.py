#!/usr/bin/env python3
"""
对比回测: 砖型图有rotation vs 无rotation
其他所有条件完全一致, 只改rotation_ok这个条件
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
    build_prepared_universe, load_omav, load_trade_calendar, load_universe, safe_num,
)

DATA = ROOT / "data"
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
TRAILING_STOP_PCT = 0.07

@dataclass
class Position:
    code: str; name: str; industry: str; strategy: str
    buy_date: str; buy_price: float; shares: int; hold_days: int
    initial_shares: int = 0; tp1_done: bool = False; tp2_done: bool = False
    trailing_stop_price: float = 0.0

def _commission(amount): return max(amount * COMMISSION_RATE, MIN_COMMISSION)
def _buy_fee(price, shares): return _commission(price * shares)
def _sell_fee(price, shares):
    amount = price * shares
    return _commission(amount) + amount * STAMP_TAX_SELL

def _sma_cn(series, n, m):
    x = safe_num(series).fillna(0.0)
    out, prev = [], None
    for v in x.tolist():
        if prev is None: prev = v
        else: prev = (m * v + (n - m) * prev) / n
        out.append(prev)
    return pd.Series(out, index=series.index)

def b1_experimental_ok(df, idx):
    sub = df.iloc[: idx + 1].copy().reset_index(drop=True)
    if len(sub) < 160: return False
    C = safe_num(sub['close']); O = safe_num(sub['open'])
    H = safe_num(sub['high']); L = safe_num(sub['low'])
    VOL = safe_num(sub['vol']).fillna(0.0)
    REAL_YANG = (C > O) & ~(C < C.shift(1))
    REAL_YIN = (C < O) & ~(C > C.shift(1))
    ll9 = L.rolling(9).min(); hh9 = H.rolling(9).max()
    RSV = (C - ll9) / (hh9 - ll9) * 100
    K = _sma_cn(RSV, 3, 1); D = _sma_cn(K, 3, 1); J = 3 * K - 2 * D
    J_OK = J <= 13
    VOL_YANG1 = (VOL * REAL_YANG.astype(int)).rolling(57).sum()
    VOL_YIN1 = (VOL * REAL_YIN.astype(int)).rolling(57).sum()
    VOL_YANG2 = (VOL * REAL_YANG.astype(int)).rolling(14).sum()
    VOL_YIN2 = (VOL * REAL_YIN.astype(int)).rolling(14).sum()
    YANGYIN_OK1 = VOL_YANG1 > 1.25 * VOL_YIN1
    YANGYIN_OK2 = VOL_YANG2 > 2.25 * VOL_YIN2
    MV = safe_num(sub.get('total_mv_billion')); MVOK = MV >= 50
    O85 = O.rolling(21).min() + 0.95 * (O.rolling(21).max() - O.rolling(21).min())
    TOP15O = O >= O85
    FD15 = (C < C.shift(1)) & (C <= O) & (VOL >= 1.2 * VOL.shift(1))
    CNT28 = ((TOP15O & FD15).astype(int)).rolling(21).sum(); GOOD28 = CNT28 <= 0
    AVG40 = VOL.rolling(40).mean()
    PLRY = (VOL > 1.95 * VOL.shift(1)) & (C > O) & (VOL > AVG40)
    PLRY_CNT = ((PLRY.astype(int)).rolling(14).sum() >= 2) | ((PLRY.astype(int)).rolling(57).sum() >= 4)
    prev_plry = PLRY.shift(1).eq(True)
    PLRY_FIRST = PLRY & (~prev_plry); PLRY_CONT = PLRY & prev_plry
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
    B1 = (sub['white_line'] >= sub['yellow_line'] * 0.985) & (C >= sub['yellow_line'] * 0.985) & A1
    return bool(B1.iloc[-1])


def run_backtest(use_rotation: bool, code_data, code_idx, meta, cal, cal_set,
                 omav_map, omav_avg5_map, rotation_map):
    """跑一次回测, use_rotation控制砖型图是否需要rotation_ok"""
    cash = INITIAL_CAPITAL
    positions: List[Position] = []
    trades = []
    nav_rows = []

    for td in cal:
        # 1) 平仓
        remain = []
        for p in positions:
            idx_map = code_idx.get(p.code, {})
            if td not in idx_map: remain.append(p); continue
            idx = idx_map[td]; df = code_data[p.code]
            buy_idx = idx_map.get(p.buy_date)
            if buy_idx is None: remain.append(p); continue
            held = idx - buy_idx
            row = df.iloc[idx]
            high = float(row["high"]); close = float(row["close"])
            yellow = safe_num(row.get("yellow_line"))
            is_b1 = p.strategy.startswith("B1")

            if not is_b1:
                if held < p.hold_days: remain.append(p); continue
                sell_price = close; fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee; cash += proceeds
                trades.append({"strategy": p.strategy, "exit_reason": "hold_expire",
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.shares), 4),
                    "buy_date": p.buy_date, "sell_date": td, "code": p.code, "name": p.name,
                    "buy_price": round(p.buy_price,4), "sell_price": round(sell_price,4), "shares": p.shares})
                continue

            if not p.tp2_done and high >= p.buy_price * (1 + B1_TP2):
                sell_price = p.buy_price * (1 + B1_TP2); fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee; cash += proceeds
                trades.append({"strategy": p.strategy, "exit_reason": "tp2",
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "buy_date": p.buy_date, "sell_date": td, "code": p.code, "name": p.name,
                    "buy_price": round(p.buy_price,4), "sell_price": round(sell_price,4), "shares": p.shares})
                continue

            if not p.tp1_done and high >= p.buy_price * (1 + B1_TP1):
                sell_shares = p.shares // 2
                if sell_shares < LOT_SIZE: sell_shares = p.shares
                sell_price = p.buy_price * (1 + B1_TP1); fee = _sell_fee(sell_price, sell_shares)
                proceeds = sell_price * sell_shares - fee; cash += proceeds
                trades.append({"strategy": p.strategy, "exit_reason": "tp1_partial",
                    "net_pnl": round(proceeds - p.buy_price * sell_shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "buy_date": p.buy_date, "sell_date": td, "code": p.code, "name": p.name,
                    "buy_price": round(p.buy_price,4), "sell_price": round(sell_price,4), "shares": sell_shares})
                p.shares -= sell_shares; p.tp1_done = True
                p.trailing_stop_price = float(row["low"]) * (1 - TRAILING_STOP_PCT)
                if p.shares <= 0: continue

            if p.tp1_done and p.trailing_stop_price > 0 and close <= p.trailing_stop_price:
                sell_price = close; fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee; cash += proceeds
                trades.append({"strategy": p.strategy, "exit_reason": "trailing_sl",
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "buy_date": p.buy_date, "sell_date": td, "code": p.code, "name": p.name,
                    "buy_price": round(p.buy_price,4), "sell_price": round(sell_price,4), "shares": p.shares})
                continue

            if B1_YELLOW_SL and pd.notna(yellow) and close < yellow:
                sell_price = close; fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee; cash += proceeds
                trades.append({"strategy": p.strategy, "exit_reason": "yellow_sl",
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "buy_date": p.buy_date, "sell_date": td, "code": p.code, "name": p.name,
                    "buy_price": round(p.buy_price,4), "sell_price": round(sell_price,4), "shares": p.shares})
                continue

            if held >= B1_MAX_HOLD_DAYS:
                sell_price = close; fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee; cash += proceeds
                trades.append({"strategy": p.strategy, "exit_reason": "max_hold",
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "buy_date": p.buy_date, "sell_date": td, "code": p.code, "name": p.name,
                    "buy_price": round(p.buy_price,4), "sell_price": round(sell_price,4), "shares": p.shares})
                continue

            remain.append(p)
        positions = remain

        # 2) 信号
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
                if code not in code_data: continue
                idx_map = code_idx[code]
                if td not in idx_map: continue
                idx = idx_map[td]; df = code_data[code]
                if idx < 25 or idx + 1 >= len(df): continue
                row = df.iloc[idx]; next_row = df.iloc[idx + 1]
                if str(next_row["trade_date"]) not in cal_set: continue

                b1 = b1_experimental_ok(df, idx)
                brick_v1 = bool(row.get("brick_raw_turn_red", False)) and bool(row.get("brick_history_ok", False))
                brick = False
                if brick_v1 and (not bear) and (not warn) and idx >= 4:
                    z = safe_num(df["brick_formula_value"]).fillna(0)
                    g = df["brick_formula_green"].fillna(False).astype(bool)
                    white = safe_num(row.get("white_line"))
                    yellow = safe_num(row.get("yellow_line"))
                    high_b = safe_num(row.get("high"))
                    if use_rotation:
                        rotation_ok = rotation_map.get((td, r.industry), False)
                    else:
                        rotation_ok = True  # 去掉rotation限制
                    brick = bool(
                        rotation_ok
                        and pd.notna(white) and pd.notna(yellow) and pd.notna(high_b)
                        and high_b >= white and white > yellow
                        and g.iloc[idx-1] and g.iloc[idx-2] and g.iloc[idx-3] and g.iloc[idx-4]
                        and z.iloc[idx-4] > z.iloc[idx-3] > z.iloc[idx-2] > z.iloc[idx-1]
                        and z.iloc[idx] >= z.iloc[idx-1])

                if warn_overlap_only and not (b1 and brick): continue
                if not (b1 or brick): continue

                sigs.append({
                    "code": code, "name": r.name, "industry": r.industry,
                    "signal_date": td, "next_date": str(next_row["trade_date"]),
                    "signal_close": float(row["close"]),
                    "next_open": float(next_row["open"]), "next_low": float(next_row["low"]),
                    "b1": b1, "brick": brick,
                    "j": float(safe_num(row.get("kdj_j"))) if pd.notna(safe_num(row.get("kdj_j"))) else 999,
                })

        # 3) 开仓
        if can_open > 0 and sigs:
            def _rank(s):
                p = 0 if (s["b1"] and s["brick"]) else (1 if s["brick"] else 2)
                return (p, s["j"])
            sigs = sorted(sigs, key=_rank)
            selected = sigs[: can_open * 2]
            opened = 0
            for s in selected:
                if opened >= can_open: break
                if s["b1"] and s["brick"]:
                    strategy = "B1+BRICK"; buy_price = min(s["signal_close"]*0.993, s["next_open"]*0.988); hold_days = 1
                elif s["brick"]:
                    strategy = "BRICK_V3"; buy_price = min(s["signal_close"]*0.995, s["next_open"]*0.99); hold_days = 1
                else:
                    strategy = "B1"; buy_price = min(s["signal_close"]*0.993, s["next_open"]*0.988); hold_days = B1_MAX_HOLD_DAYS

                if s["next_low"] > buy_price: continue

                # B1纯前2日过滤
                if s["b1"] and not s["brick"]:
                    try:
                        signal_idx = code_idx[s["code"]][s["signal_date"]]
                        sdf = code_data[s["code"]]
                        p1 = float(sdf.iloc[signal_idx-1].get("pct_chg",0)) if signal_idx>=1 else 0
                        p2 = float(sdf.iloc[signal_idx-2].get("pct_chg",0)) if signal_idx>=2 else 0
                    except: p1 = p2 = 0
                    if p1 <= -1.5 and p2 <= -1.5: continue

                slots_left = max(1, can_open - opened)
                budget = cash / slots_left
                avg5_prev = omav_avg5_map.get(s["signal_date"])
                if (s["b1"] and (not s["brick"])) or (s["b1"] and s["brick"]):
                    if avg5_prev is not None:
                        try:
                            avg5_v = float(avg5_prev)
                            if 1 < avg5_v <= 2 and not (s["b1"] and s["brick"]): budget *= 0.5
                        except: pass

                shares = int(budget // buy_price // LOT_SIZE) * LOT_SIZE
                if shares <= 0: continue
                fee = _buy_fee(buy_price, shares)
                cost = buy_price * shares + fee
                if cost > cash: continue

                cash -= cost
                positions.append(Position(code=s["code"], name=s["name"], industry=s["industry"],
                    strategy=strategy, buy_date=s["next_date"], buy_price=buy_price,
                    shares=shares, hold_days=hold_days, initial_shares=shares))
                trades.append({"strategy": strategy, "exit_reason": "BUY",
                    "buy_date": s["next_date"], "sell_date": None,
                    "buy_price": round(buy_price,4), "sell_price": None, "shares": shares,
                    "code": s["code"], "name": s["name"], "b1": s["b1"], "brick": s["brick"]})
                opened += 1

        # NAV
        mv = 0.0
        for p in positions:
            idx_map = code_idx.get(p.code, {})
            if td in idx_map: mv += float(code_data[p.code].iloc[idx_map[td]]["close"]) * p.shares
            else: mv += p.buy_price * p.shares
        nav_rows.append({"date": td, "cash": cash, "mv": mv, "total": cash + mv})

    # 统计
    sells = [t for t in trades if t["exit_reason"] != "BUY"]
    buys = [t for t in trades if t["exit_reason"] == "BUY"]
    brick_buys = [t for t in buys if t.get("brick")]
    brick_sells = [t for t in sells if "BRICK" in t.get("strategy","")]
    b1_buys = [t for t in buys if t.get("b1") and not t.get("brick")]
    b1_sells = [t for t in sells if t["strategy"] == "B1"]
    both_buys = [t for t in buys if t.get("b1") and t.get("brick")]
    both_sells = [t for t in sells if "B1+BRICK" in t.get("strategy","")]

    final = nav_rows[-1]["total"] if nav_rows else INITIAL_CAPITAL
    total_ret = (final / INITIAL_CAPITAL - 1) * 100
    win_trades = [t for t in sells if t.get("net_pnl",0) > 0]
    lose_trades = [t for t in sells if t.get("net_pnl",0) <= 0]
    wr = len(win_trades) / len(sells) * 100 if sells else 0

    # max drawdown
    peak = INITIAL_CAPITAL; max_dd = 0
    for n in nav_rows:
        t = n["total"]
        if t > peak: peak = t
        dd = (peak - t) / peak * 100
        if dd > max_dd: max_dd = dd

    # 砖型图单独统计
    brick_win = [t for t in brick_sells if t.get("net_pnl",0) > 0]
    brick_wr = len(brick_win) / len(brick_sells) * 100 if brick_sells else 0
    brick_pnl = sum(t.get("net_pnl",0) for t in brick_sells)

    # B1单独统计
    b1_all_sells = b1_sells + both_sells
    b1_win = [t for t in b1_all_sells if t.get("net_pnl",0) > 0]
    b1_wr = len(b1_win) / len(b1_all_sells) * 100 if b1_all_sells else 0
    b1_pnl = sum(t.get("net_pnl",0) for t in b1_all_sells)

    return {
        "total_return": round(total_ret, 2),
        "final_equity": round(final, 2),
        "total_trades": len(sells),
        "win_rate": round(wr, 2),
        "max_drawdown": round(max_dd, 2),
        "brick_trades": len(brick_sells),
        "brick_winrate": round(brick_wr, 2),
        "brick_pnl": round(brick_pnl, 2),
        "b1_trades": len(b1_all_sells),
        "b1_winrate": round(b1_wr, 2),
        "b1_pnl": round(b1_pnl, 2),
        "both_trades": len(both_sells),
    }


def main():
    omav = load_omav(DATA)
    omav_map = omav.set_index("trade_date").to_dict("index")
    omav_avg5_map = {}
    if "trade_date" in omav.columns:
        om2 = omav.copy().sort_values("trade_date").reset_index(drop=True)
        val_col = "omav" if "omav" in om2.columns else ("omav_value" if "omav_value" in om2.columns else None)
        if val_col:
            om2[val_col] = safe_num(om2[val_col])
            om2["avg5_prev"] = om2[val_col].shift(1).rolling(5).mean()
            omav_avg5_map = om2.set_index("trade_date")["avg5_prev"].to_dict()

    cal = load_trade_calendar(START_DATE, END_DATE, DATA)
    cal_set = set(cal)
    meta = load_universe(DATA)

    print("[INFO] loading prepared universe...")
    meta, code_data, code_idx, rotation_map = build_prepared_universe(
        START_DATE, END_DATE, DATA, min_rows=40)
    print(f"[INFO] usable codes: {len(code_data)}, trading days: {len(cal)}")

    # === A: 有rotation (BaseLine原版) ===
    print("\n[A] Running WITH rotation...")
    res_a = run_backtest(True, code_data, code_idx, meta, cal, cal_set,
                         omav_map, omav_avg5_map, rotation_map)

    # === B: 无rotation ===
    print("[B] Running WITHOUT rotation...")
    res_b = run_backtest(False, code_data, code_idx, meta, cal, cal_set,
                         omav_map, omav_avg5_map, rotation_map)

    print("\n" + "=" * 60)
    print("对比: 砖型图 rotation_ok 的影响")
    print("=" * 60)
    print(f"{'指标':<20} {'有rotation':>14} {'无rotation':>14} {'差值':>10}")
    print("-" * 60)
    for key in ["total_return", "final_equity", "total_trades", "win_rate",
                "max_drawdown", "brick_trades", "brick_winrate", "brick_pnl",
                "b1_trades", "b1_winrate", "b1_pnl", "both_trades"]:
        a, b = res_a[key], res_b[key]
        diff = round(b - a, 2) if isinstance(a, (int, float)) else "-"
        print(f"{key:<20} {a:>14} {b:>14} {diff:>10}")

    print(f"\n{'='*60}")
    print(f"结论: rotation过滤掉{(res_b['brick_trades']-res_a['brick_trades'])}笔砖型图交易")
    if res_a['total_return'] > res_b['total_return']:
        print(f"rotation提升了总收益 {res_a['total_return']-res_b['total_return']:.2f}%")
    else:
        print(f"rotation拖累了总收益 {res_b['total_return']-res_a['total_return']:.2f}%")

if __name__ == "__main__":
    main()
