#!/usr/bin/env python3
"""
买点V1对比回测
在同一universe、信号、V4-A过滤、OMAV环境下:
  baseline: 现有硬编码买点 (B1/共振: min(C*0.993,O*0.988); 砖: min(C*0.995,O*0.99))
  v1:       买点计划V1 (信号强度修正 + 场景应对)

输出:
  outputs/entry_v1_comparison_summary.json
  outputs/entry_v1_baseline_trades.csv
  outputs/entry_v1_v1_trades.csv
  outputs/entry_v1_baseline_nav.csv
  outputs/entry_v1_v1_nav.csv
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from quant.sim_replay_common import (
    V4_EXCLUDED_INDUSTRIES,
    build_prepared_universe,
    load_omav,
    load_trade_calendar,
    load_universe,
    prepare_code_df,
    safe_num,
)
from quant.entry_plan_v1 import compute_entry_v1
DATA = ROOT / "data"
OUT = ROOT / "outputs"

START_DATE = "20230101"
END_DATE = "20260403"
INITIAL_CAPITAL = 100_000.0
LOT_SIZE = 100
COMMISSION_RATE = 0.000086
MIN_COMMISSION = 5.0
STAMP_TAX_SELL = 0.0005
B1_MAX_HOLD_DAYS = 10

SHORT_TAG = "entry_v1"


# ── Position ────────────────────────────────────────
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


# ── Fee helpers ─────────────────────────────────────
def _commission(amount: float) -> float:
    return max(amount * COMMISSION_RATE, MIN_COMMISSION)


def _buy_fee(price: float, shares: int) -> float:
    return _commission(price * shares)


def _sell_fee(price: float, shares: int) -> float:
    amount = price * shares
    return _commission(amount) + amount * STAMP_TAX_SELL


# ── B1 signal (same as main backtest) ──────────────
def _sma_cn(series: pd.Series, n: int, m: int) -> pd.Series:
    x = safe_num(series).fillna(0.0)
    out: list = []
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
    C = safe_num(sub["close"])
    O = safe_num(sub["open"])
    H = safe_num(sub["high"])
    L = safe_num(sub["low"])
    VOL = safe_num(sub["vol"]).fillna(0.0)
    REAL_YANG = (C > O) & ~(C < C.shift(1))
    REAL_YIN = (C < O) & ~(C > C.shift(1))
    ll9 = L.rolling(9).min()
    hh9 = H.rolling(9).max()
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
    MV = safe_num(sub.get("total_mv_billion"))
    MVOK = MV >= 50
    O85 = O.rolling(21).min() + 0.95 * (O.rolling(21).max() - O.rolling(21).min())
    TOP15O = O >= O85
    FD15 = (C < C.shift(1)) & (C <= O) & (VOL >= 1.2 * VOL.shift(1))
    CNT28 = ((TOP15O & FD15).astype(int)).rolling(21).sum()
    GOOD28 = CNT28 <= 0
    AVG40 = VOL.rolling(40).mean()
    PLRY = (VOL > 1.95 * VOL.shift(1)) & (C > O) & (VOL > AVG40)
    PLRY_CNT = (PLRY.astype(int).rolling(14).sum() >= 2) | (
        PLRY.astype(int).rolling(57).sum() >= 4
    )
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
    A1 = (PLRY_CNT & YANGYIN_OK1 & J_OK & MVOK & GOOD28 & THREE_SUM_OK & MAX28_OK) | (
        PLRY_CNT & YANGYIN_OK2 & J_OK & MVOK & GOOD28 & MAX28_OK
    )
    HMSHORTWL = sub["white_line"]
    HMLONGYL = sub["yellow_line"]
    B1 = (HMSHORTWL >= HMLONGYL * 0.985) & (C >= HMLONGYL * 0.985) & A1
    return bool(B1.iloc[-1])


# ── Signal collection (shared) ─────────────────────
def _collect_signals(
    td: str,
    meta: pd.DataFrame,
    code_data: dict,
    code_idx: dict,
    rotation_map: dict,
    cal_set: set,
    bear: bool,
    warn: bool,
) -> list:
    """Generate signals for a trading day — identical for both baseline and V1."""
    sigs = []
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

        # BRICK_V3
        brick_v1 = bool(row.get("brick_raw_turn_red", False)) and bool(
            row.get("brick_history_ok", False)
        )
        brick = False
        if brick_v1 and (not bear) and (not warn) and idx >= 4:
            z = safe_num(df["brick_formula_value"]).fillna(0)
            g = df["brick_formula_green"].fillna(False).astype(bool)
            white = safe_num(row.get("white_line"))
            yellow = safe_num(row.get("yellow_line"))
            high = safe_num(row.get("high"))
            rotation_ok = rotation_map.get((td, r.industry), False)
            brick = bool(
                rotation_ok
                and pd.notna(white)
                and pd.notna(yellow)
                and pd.notna(high)
                and high >= white
                and white > yellow
                and g.iloc[idx - 1]
                and g.iloc[idx - 2]
                and g.iloc[idx - 3]
                and g.iloc[idx - 4]
                and z.iloc[idx - 4] > z.iloc[idx - 3] > z.iloc[idx - 2] > z.iloc[idx - 1]
                and z.iloc[idx] >= z.iloc[idx - 1]
            )

        if warn and not bear and not (b1 and brick):
            continue
        if not (b1 or brick):
            continue

        # Compute extra features for V1
        vol_series = safe_num(df["vol"]).fillna(0.0)
        avg40 = vol_series.rolling(40).mean()
        vol_ratio = float(vol_series.iloc[idx] / avg40.iloc[idx]) if avg40.iloc[idx] > 0 else 1.0

        j_val = float(safe_num(row.get("kdj_j", 999)))
        if pd.isna(j_val):
            j_val = 999.0

        green_streak = int(safe_num(row.get("brick_green_streak", 0)) or 0)

        sigs.append(
            {
                "code": code,
                "name": r.name,
                "industry": r.industry,
                "signal_date": td,
                "next_date": str(next_row["trade_date"]),
                "signal_close": float(row["close"]),
                "signal_pct": float(safe_num(row.get("pct_chg", 0))),
                "next_open": float(next_row["open"]),
                "next_low": float(next_row["low"]),
                "next_high": float(next_row["high"]),
                "b1": b1,
                "brick": brick,
                "j": j_val,
                "vol_ratio": vol_ratio,
                "green_streak": green_streak,
                "white_line": float(safe_num(row.get("white_line", 0)) or 0),
                "yellow_line": float(safe_num(row.get("yellow_line", 0)) or 0),
            }
        )
    return sigs


# ── Sort signals (shared) ──────────────────────────
def _sort_signals(sigs: list) -> list:
    def _rank(s):
        p = 0 if (s["b1"] and s["brick"]) else (1 if s["brick"] else 2)
        return (p, s["j"])

    return sorted(sigs, key=_rank)


# ── V4-A + narrow fix (shared) ─────────────────────
def _v4a_filter(s: dict, code_idx: dict, code_data: dict) -> bool:
    """Return True if signal passes V4-A + narrow fix."""
    if s["b1"] and not s["brick"]:
        try:
            signal_idx = code_idx[s["code"]][s["signal_date"]]
            signal_df = code_data[s["code"]]
            prev1_pct = float(signal_df.iloc[signal_idx - 1].get("pct_chg", 0.0)) if signal_idx >= 1 else 0.0
            prev2_pct = float(signal_df.iloc[signal_idx - 2].get("pct_chg", 0.0)) if signal_idx >= 2 else 0.0
        except Exception:
            prev1_pct = 0.0
            prev2_pct = 0.0
        if (prev1_pct <= -1.0) and (prev2_pct <= -1.5):
            return False
        try:
            signal_idx = code_idx[s["code"]][s["signal_date"]]
            signal_df = code_data[s["code"]]
            wl = float(signal_df.iloc[signal_idx].get("white_line", 0.0) or 0.0)
            yl = float(signal_df.iloc[signal_idx].get("yellow_line", 0.0) or 0.0)
            cp = float(signal_df.iloc[signal_idx].get("close", 0.0) or 0.0)
            if wl > 0 and yl > 0:
                if (cp / wl < 0.96) and (wl / yl > 1.09):
                    return False
        except Exception:
            pass
    return True


# ── Run one backtest variant ────────────────────────
def _run_backtest(
    mode: str,  # "baseline" or "v1"
    meta: pd.DataFrame,
    code_data: dict,
    code_idx: dict,
    rotation_map: dict,
    cal: list,
    omav_map: dict,
    omav_avg5_map: dict,
    cal_set: set,
) -> dict:
    """Run a single backtest variant and return summary + trades + nav."""
    cash = INITIAL_CAPITAL
    positions: List[Position] = []
    trades = []
    nav_rows = []

    for td_i, td in enumerate(cal):
        if td_i % 100 == 0:
            print("  [%s] day %d/%d pos=%d cash=%.0f" % (mode, td_i, len(cal), len(positions), cash), flush=True)
        # 1) Close positions
        remain: List[Position] = []
        for p in positions:
            idx_map = code_idx.get(p.code, {})
            if td not in idx_map:
                remain.append(p)
                continue
            idx = idx_map[td]
            df = code_data[p.code]
            buy_idx = idx_map.get(p.buy_date)
            if buy_idx is None:
                remain.append(p)
                continue
            held = idx - buy_idx
            if held < p.hold_days:
                remain.append(p)
                continue
            sell_price = float(df.iloc[idx]["close"])
            fee = _sell_fee(sell_price, p.shares)
            proceeds = sell_price * p.shares - fee
            cash += proceeds
            trades.append(
                {
                    "code": p.code,
                    "name": p.name,
                    "industry": p.industry,
                    "strategy": p.strategy,
                    "buy_date": p.buy_date,
                    "sell_date": td,
                    "buy_price": round(p.buy_price, 4),
                    "sell_price": round(sell_price, 4),
                    "shares": p.shares,
                    "gross_pnl": round((sell_price - p.buy_price) * p.shares, 4),
                    "fees": round(_buy_fee(p.buy_price, p.shares) + fee, 4),
                    "net_pnl": round(
                        proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.shares), 4
                    ),
                }
            )
        positions = remain

        # 2) Environment
        om = omav_map.get(td, {})
        bear = str(om.get("omav_bear_regime_flag", "False")).lower() == "true"
        warn = str(om.get("omav_rotation_warning_flag", "False")).lower() == "true"
        max_new = 0 if bear else (1 if warn else 3)
        max_total_pos = 1 if warn else 3
        free_slots = max(0, max_total_pos - len(positions))
        can_open = min(max_new, free_slots)

        if can_open <= 0:
            # Record nav
            mv = _market_value(positions, td, code_idx, code_data)
            nav_rows.append(
                {
                    "trade_date": td,
                    "cash": round(cash, 2),
                    "market_value": round(mv, 2),
                    "total_equity": round(cash + mv, 2),
                    "positions": len(positions),
                }
            )
            continue

        # 3) Collect signals (shared)
        sigs = _collect_signals(
            td, meta, code_data, code_idx, rotation_map, cal_set, bear, warn
        )
        if not sigs:
            mv = _market_value(positions, td, code_idx, code_data)
            nav_rows.append(
                {
                    "trade_date": td,
                    "cash": round(cash, 2),
                    "market_value": round(mv, 2),
                    "total_equity": round(cash + mv, 2),
                    "positions": len(positions),
                }
            )
            continue

        sigs = _sort_signals(sigs)
        selected = sigs[: can_open * 2]

        opened = 0
        for s in selected:
            if opened >= can_open:
                break

            # V4-A + narrow fix
            if not _v4a_filter(s, code_idx, code_data):
                continue

            # ── BUY PRICE CALCULATION ──
            if mode == "baseline":
                # 现有硬编码
                if s["b1"] and s["brick"]:
                    strategy = "B1+BRICK"
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
            else:
                # V1 买点
                plan = compute_entry_v1(
                    is_b1=s["b1"],
                    is_brick=s["brick"],
                    signal_close=s["signal_close"],
                    pct_chg=s["signal_pct"],
                    vol_ratio=s["vol_ratio"],
                    j_value=s["j"],
                    green_streak=s["green_streak"],
                    white_line=s["white_line"],
                    yellow_line=s["yellow_line"],
                    next_open=s["next_open"],
                    next_low=s["next_low"],
                )
                if plan is None or plan.buy_price is None:
                    continue
                strategy = plan.strategy_type
                buy_price = plan.buy_price
                hold_days = plan.hold_days

            # Fill check
            if s["next_low"] > buy_price:
                continue

            # avg5 deweight (shared logic)
            slots_left = max(1, can_open - opened)
            budget = cash / slots_left
            avg5_prev = omav_avg5_map.get(s["signal_date"])
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
            positions.append(
                Position(
                    code=s["code"],
                    name=s["name"],
                    industry=s["industry"],
                    strategy=strategy,
                    buy_date=s["next_date"],
                    buy_price=buy_price,
                    shares=shares,
                    hold_days=hold_days,
                    initial_shares=shares,
                )
            )
            opened += 1

        # 4) NAV
        mv = _market_value(positions, td, code_idx, code_data)
        nav_rows.append(
            {
                "trade_date": td,
                "cash": round(cash, 2),
                "market_value": round(mv, 2),
                "total_equity": round(cash + mv, 2),
                "positions": len(positions),
            }
        )

    # Final summary
    nav = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)
    final_equity = float(nav.iloc[-1]["total_equity"]) if not nav.empty else INITIAL_CAPITAL
    total_return = (final_equity / INITIAL_CAPITAL - 1) * 100

    return {
        "nav": nav,
        "trades_df": trades_df,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return, 2),
        "trade_count": len(trades_df),
        "win_rate_pct": round(float((trades_df["net_pnl"] > 0).mean() * 100), 2)
        if not trades_df.empty
        else 0.0,
    }


def _market_value(
    positions: List[Position], td: str, code_idx: dict, code_data: dict
) -> float:
    mv = 0.0
    for p in positions:
        idx_map = code_idx.get(p.code, {})
        if td in idx_map:
            px = float(code_data[p.code].iloc[idx_map[td]]["close"])
            mv += px * p.shares
        else:
            mv += p.buy_price * p.shares
    return mv


# ── Main ────────────────────────────────────────────
def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("[INFO] loading OMAV + calendar...", flush=True)
    omav = load_omav(DATA)
    omav_map = omav.set_index("trade_date").to_dict("index")
    omav_avg5_map = {}
    om2 = omav.copy().sort_values("trade_date").reset_index(drop=True)
    val_col = "omav" if "omav" in om2.columns else ("omav_value" if "omav_value" in om2.columns else None)
    if val_col is not None:
        om2[val_col] = safe_num(om2[val_col])
        om2["avg5_prev"] = om2[val_col].shift(1).rolling(5).mean()
        omav_avg5_map = om2.set_index("trade_date")["avg5_prev"].to_dict()

    cal = load_trade_calendar(START_DATE, END_DATE, DATA)
    cal_set = set(cal)

    print("[INFO] building universe (V4 hard blacklist)...", flush=True)
    meta, code_data, code_idx, rotation_map = build_prepared_universe(
        START_DATE,
        END_DATE,
        DATA,
        min_rows=40,
        excluded_industries=V4_EXCLUDED_INDUSTRIES,
    )
    print("[INFO] usable codes: %d" % len(code_data), flush=True)

    # ── Run baseline ──
    print("[INFO] === BASELINE (hardcoded entry) ===", flush=True)
    bl = _run_backtest(
        "baseline", meta, code_data, code_idx, rotation_map,
        cal, omav_map, omav_avg5_map, cal_set,
    )
    print("  total_return: %.2f%%  trades: %d  win_rate: %.1f%%" % (
        bl["total_return_pct"], bl["trade_count"], bl["win_rate_pct"]
    ), flush=True)

    # ── Run V1 ──
    print("[INFO] === V1 (entry plan v1) ===", flush=True)
    v1 = _run_backtest(
        "v1", meta, code_data, code_idx, rotation_map,
        cal, omav_map, omav_avg5_map, cal_set,
    )
    print("  total_return: %.2f%%  trades: %d  win_rate: %.1f%%" % (
        v1["total_return_pct"], v1["trade_count"], v1["win_rate_pct"]
    ), flush=True)

    # ── Per-strategy breakdown ──
    def _strategy_breakdown(trades_df: pd.DataFrame) -> dict:
        if trades_df.empty:
            return {}
        grp = trades_df.groupby("strategy").agg(
            count=("net_pnl", "size"),
            total_pnl=("net_pnl", "sum"),
            win_rate=("net_pnl", lambda x: round((x > 0).mean() * 100, 1)),
            avg_pnl=("net_pnl", "mean"),
        ).to_dict("index")
        return {k: {kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in grp.items()}

    # ── Save outputs ──
    bl["nav"].to_csv(OUT / ("%s_baseline_nav.csv" % SHORT_TAG), index=False, encoding="utf-8-sig")
    bl["trades_df"].to_csv(OUT / ("%s_baseline_trades.csv" % SHORT_TAG), index=False, encoding="utf-8-sig")
    v1["nav"].to_csv(OUT / ("%s_v1_nav.csv" % SHORT_TAG), index=False, encoding="utf-8-sig")
    v1["trades_df"].to_csv(OUT / ("%s_v1_trades.csv" % SHORT_TAG), index=False, encoding="utf-8-sig")

    summary = {
        "start_date": START_DATE,
        "end_date": END_DATE,
        "initial_capital": INITIAL_CAPITAL,
        "baseline": {
            "final_equity": bl["final_equity"],
            "total_return_pct": bl["total_return_pct"],
            "trade_count": bl["trade_count"],
            "win_rate_pct": bl["win_rate_pct"],
            "strategy_breakdown": _strategy_breakdown(bl["trades_df"]),
        },
        "v1": {
            "final_equity": v1["final_equity"],
            "total_return_pct": v1["total_return_pct"],
            "trade_count": v1["trade_count"],
            "win_rate_pct": v1["win_rate_pct"],
            "strategy_breakdown": _strategy_breakdown(v1["trades_df"]),
        },
        "diff": {
            "return_pct": round(v1["total_return_pct"] - bl["total_return_pct"], 2),
            "trade_count": v1["trade_count"] - bl["trade_count"],
            "win_rate_pct": round(v1["win_rate_pct"] - bl["win_rate_pct"], 2),
        },
    }

    summary_path = OUT / ("%s_comparison_summary.json" % SHORT_TAG)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=" * 60)
    print("COMPARISON SUMMARY")
    print("=" * 60)
    print("Baseline: %.2f%%  (%d trades, WR %.1f%%)" % (
        bl["total_return_pct"], bl["trade_count"], bl["win_rate_pct"]))
    print("V1:       %.2f%%  (%d trades, WR %.1f%%)" % (
        v1["total_return_pct"], v1["trade_count"], v1["win_rate_pct"]))
    print("Diff:     %+.2f%%  (%+d trades, WR %+.1f%%)" % (
        summary["diff"]["return_pct"],
        summary["diff"]["trade_count"],
        summary["diff"]["win_rate_pct"],
    ))
    print()
    print("Saved to: %s" % summary_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
