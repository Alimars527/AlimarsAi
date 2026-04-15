#!/usr/bin/env python3
"""
Baseline年度回测
  - 策略组合: B1+BRICK(hold1) + BRICK_V3(hold1) + B1_EXPERIMENTAL(hold最多10天)
  - 初始资金: 100,000
  - 区间: 20230101 ~ 20260403
  - 输出: 总计 + 逐年(收益/胜率/盈亏/笔数)
  - 分段checkpoint: 每年结束保存中间状态，断点可续跑
  - 进度文件: outputs/baseline_annual_progress.txt
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, asdict
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

DATA = ROOT / "data"
OUT = ROOT / "outputs"
CKPT_DIR = OUT / "checkpoints"

START_DATE = "20230101"
END_DATE = "20260403"
INITIAL_CAPITAL = 100_000.0
LOT_SIZE = 100
COMMISSION_RATE = 0.000086
MIN_COMMISSION = 5.0
STAMP_TAX_SELL = 0.0005
B1_MAX_HOLD_DAYS = 10

PROGRESS_FILE = OUT / "baseline_annual_progress.txt"
RESULT_FILE = OUT / "baseline_annual_result.json"
TRADES_FILE = OUT / "baseline_annual_trades.csv"
NAV_FILE = OUT / "baseline_annual_nav.csv"


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


# ── Fee helpers ─────────────────────────────────────
def _commission(amount: float) -> float:
    return max(amount * COMMISSION_RATE, MIN_COMMISSION)


def _buy_fee(price: float, shares: int) -> float:
    return _commission(price * shares)


def _sell_fee(price: float, shares: int) -> float:
    amount = price * shares
    return _commission(amount) + amount * STAMP_TAX_SELL


# ── B1 signal ───────────────────────────────────────
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


# ── Signal collection ───────────────────────────────
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

        sigs.append({
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
            "j": float(safe_num(row.get("kdj_j", 999)) or 999),
            "vol_ratio": 0.0,  # placeholder, not needed for baseline
            "green_streak": 0,
            "white_line": float(safe_num(row.get("white_line", 0)) or 0),
            "yellow_line": float(safe_num(row.get("yellow_line", 0)) or 0),
        })
    return sigs


# ── Sort signals ────────────────────────────────────
def _sort_signals(sigs: list) -> list:
    def _rank(s):
        p = 0 if (s["b1"] and s["brick"]) else (1 if s["brick"] else 2)
        return (p, s["j"])
    return sorted(sigs, key=_rank)


# ── V4-A + narrow fix ──────────────────────────────
def _v4a_filter(s: dict, code_idx: dict, code_data: dict) -> bool:
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


# ── Market value ────────────────────────────────────
def _market_value(positions: List[Position], td: str, code_idx: dict, code_data: dict) -> float:
    mv = 0.0
    for p in positions:
        idx_map = code_idx.get(p.code, {})
        if td in idx_map:
            px = float(code_data[p.code].iloc[idx_map[td]]["close"])
            mv += px * p.shares
        else:
            mv += p.buy_price * p.shares
    return mv


# ── Progress file ───────────────────────────────────
def _write_progress(msg: str):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def _reset_progress():
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text("--- Baseline Annual Backtest Progress ---\n", encoding="utf-8")


# ── Checkpoint save/load ────────────────────────────
def _save_checkpoint(
    year: str,
    cash: float,
    positions: List[Position],
    trades: list,
    nav_rows: list,
    year_start_equity: float,
):
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    ckpt = {
        "year": year,
        "cash": round(cash, 2),
        "positions": [asdict(p) for p in positions],
        "trades_count": len(trades),
        "nav_rows_count": len(nav_rows),
        "year_start_equity": round(year_start_equity, 2),
    }
    path = CKPT_DIR / f"baseline_annual_{year}.json"
    path.write_text(json.dumps(ckpt, ensure_ascii=False, indent=2), encoding="utf-8")
    # Also save trades and nav accumulated so far
    pd.DataFrame(trades).to_csv(CKPT_DIR / f"baseline_annual_trades_thru_{year}.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(nav_rows).to_csv(CKPT_DIR / f"baseline_annual_nav_thru_{year}.csv", index=False, encoding="utf-8-sig")


def _find_latest_checkpoint() -> Optional[str]:
    """Return the latest completed year string, or None."""
    if not CKPT_DIR.exists():
        return None
    years = sorted(
        p.stem.split("_")[-1]
        for p in CKPT_DIR.glob("baseline_annual_2*.json")
    )
    return years[-1] if years else None


def _load_checkpoint(year: str) -> Optional[dict]:
    path = CKPT_DIR / f"baseline_annual_{year}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_trades_nav_thru(year: str):
    trades_path = CKPT_DIR / f"baseline_annual_trades_thru_{year}.csv"
    nav_path = CKPT_DIR / f"baseline_annual_nav_thru_{year}.csv"
    trades = pd.read_csv(trades_path, encoding="utf-8-sig").to_dict("records") if trades_path.exists() else []
    nav_rows = pd.read_csv(nav_path, encoding="utf-8-sig").to_dict("records") if nav_path.exists() else []
    return trades, nav_rows


# ── Annual stats helper ─────────────────────────────
def _annual_stats(trades: list, year: str, year_start_equity: float) -> dict:
    yt = [t for t in trades if t.get("sell_date", "")[:4] == year]
    if not yt:
        return {
            "year": year,
            "trades": 0,
            "win_rate_pct": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "return_pct": 0.0,
            "year_start_equity": round(year_start_equity, 2),
            "year_end_equity": round(year_start_equity, 2),
            "strategy_breakdown": {},
        }
    df = pd.DataFrame(yt)
    wins = (df["net_pnl"] > 0).sum()
    total_pnl = float(df["net_pnl"].sum())
    # year_end_equity = year_start + all net_pnl for sells in this year
    year_end_equity = year_start_equity + total_pnl
    return_pct = (year_end_equity / year_start_equity - 1) * 100 if year_start_equity > 0 else 0.0

    # per-strategy breakdown
    grp = df.groupby("strategy").agg(
        count=("net_pnl", "size"),
        total_pnl=("net_pnl", "sum"),
        win_rate=("net_pnl", lambda x: round((x > 0).mean() * 100, 1)),
        avg_pnl=("net_pnl", "mean"),
    ).to_dict("index")
    breakdown = {k: {kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in grp.items()}

    return {
        "year": year,
        "trades": len(yt),
        "win_rate_pct": round(wins / len(yt) * 100, 2),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / len(yt), 2),
        "return_pct": round(return_pct, 2),
        "year_start_equity": round(year_start_equity, 2),
        "year_end_equity": round(year_end_equity, 2),
        "strategy_breakdown": breakdown,
    }


# ── Main backtest ───────────────────────────────────
def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    _reset_progress()

    # ── Check for checkpoint resume ──
    resume_year = _find_latest_checkpoint()
    if resume_year:
        print(f"[INFO] Found checkpoint thru {resume_year}, resuming...", flush=True)
        _write_progress(f"[RESUME] Found checkpoint thru {resume_year}")
        ckpt = _load_checkpoint(resume_year)
        trades, nav_rows = _load_trades_nav_thru(resume_year)
        cash = ckpt["cash"]
        positions = [Position(**p) for p in ckpt["positions"]]
        year_start_equity_map = {}  # we'll rebuild annual stats from trades only
        print(f"  cash={cash:.0f} positions={len(positions)} trades={len(trades)}", flush=True)
    else:
        print("[INFO] No checkpoint, starting fresh", flush=True)
        _write_progress("[START] Fresh run")
        cash = INITIAL_CAPITAL
        positions: List[Position] = []
        trades = []
        nav_rows = []
        resume_year = None

    # ── Load data ──
    print("[INFO] loading OMAV + calendar...", flush=True)
    _write_progress("[LOAD] OMAV + calendar...")
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
    _write_progress("[LOAD] Building universe...")
    meta, code_data, code_idx, rotation_map = build_prepared_universe(
        START_DATE, END_DATE, DATA,
        min_rows=40,
        excluded_industries=V4_EXCLUDED_INDUSTRIES,
    )
    print(f"[INFO] usable codes: {len(code_data)}", flush=True)
    _write_progress(f"[READY] {len(code_data)} codes, {len(cal)} trading days")

    # ── Determine start index in calendar ──
    if resume_year:
        # Skip to the year AFTER the checkpoint
        skip_thru = str(int(resume_year) + 1) + "0101"
        start_i = 0
        for i, d in enumerate(cal):
            if d >= skip_thru:
                start_i = i
                break
        else:
            start_i = len(cal)
        print(f"  skipping to index {start_i} (date={cal[start_i] if start_i < len(cal) else 'END'})", flush=True)
    else:
        start_i = 0

    # ── Year boundaries ──
    all_years = sorted(set(d[:4] for d in cal))
    # Track year_start_equity for each year
    year_start_equity_map = {}
    if resume_year:
        # For resumed runs, we reconstruct year_start from checkpoint
        # The checkpoint thru year X means all trades up to X are done
        # Year start for X+1 = cash at end of X + positions MV at end of X
        # Approximate: use checkpoint cash + position MV
        next_year = str(int(resume_year) + 1)
        mv = _market_value(positions, cal[start_i - 1] if start_i > 0 else cal[0], code_idx, code_data)
        year_start_equity_map[next_year] = cash + mv
    else:
        year_start_equity_map[all_years[0]] = INITIAL_CAPITAL

    # ── Trading loop ──
    current_year = None
    total_days = len(cal) - start_i

    for td_i in range(start_i, len(cal)):
        td = cal[td_i]
        yr = td[:4]

        elapsed = td_i - start_i + 1
        if elapsed % 20 == 0 or elapsed == 1:
            pct = elapsed / total_days * 100
            msg = f"[{yr}] day {elapsed}/{total_days} ({pct:.1f}%) pos={len(positions)} cash={cash:.0f}"
            print(msg, flush=True)
            _write_progress(msg)

        # ── Year transition: checkpoint + record year boundary ──
        if yr != current_year:
            if current_year is not None:
                # Save checkpoint for previous year
                _save_checkpoint(current_year, cash, positions, trades, nav_rows, year_start_equity_map.get(current_year, INITIAL_CAPITAL))
                # Compute year_start_equity for new year
                mv = _market_value(positions, cal[td_i - 1], code_idx, code_data)
                year_start_equity_map[yr] = cash + mv
                print(f"  === Year {current_year} done, checkpoint saved. New year equity={year_start_equity_map[yr]:.0f} ===", flush=True)
                _write_progress(f"=== Year {current_year} checkpoint saved ===")
            current_year = yr

        # 1) Close positions whose hold_days met
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
            trades.append({
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
                "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.shares), 4),
            })
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
            mv = _market_value(positions, td, code_idx, code_data)
            nav_rows.append({"trade_date": td, "cash": round(cash, 2), "market_value": round(mv, 2), "total_equity": round(cash + mv, 2), "positions": len(positions)})
            continue

        # 3) Collect signals
        sigs = _collect_signals(td, meta, code_data, code_idx, rotation_map, cal_set, bear, warn)
        if not sigs:
            mv = _market_value(positions, td, code_idx, code_data)
            nav_rows.append({"trade_date": td, "cash": round(cash, 2), "market_value": round(mv, 2), "total_equity": round(cash + mv, 2), "positions": len(positions)})
            continue

        sigs = _sort_signals(sigs)
        selected = sigs[:can_open * 2]

        opened = 0
        for s in selected:
            if opened >= can_open:
                break

            if not _v4a_filter(s, code_idx, code_data):
                continue

            # ── BUY PRICE (baseline hardcoded) ──
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

            # Fill check
            if s["next_low"] > buy_price:
                continue

            # avg5 deweight
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
            positions.append(Position(
                code=s["code"], name=s["name"], industry=s["industry"],
                strategy=strategy, buy_date=s["next_date"],
                buy_price=buy_price, shares=shares, hold_days=hold_days,
                initial_shares=shares,
            ))
            opened += 1

        # 4) NAV
        mv = _market_value(positions, td, code_idx, code_data)
        nav_rows.append({"trade_date": td, "cash": round(cash, 2), "market_value": round(mv, 2), "total_equity": round(cash + mv, 2), "positions": len(positions)})

    # ── Final checkpoint ──
    if current_year:
        _save_checkpoint(current_year, cash, positions, trades, nav_rows, year_start_equity_map.get(current_year, INITIAL_CAPITAL))

    # ── Build results ──
    elapsed_sec = time.time() - t0
    nav = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)
    final_equity = float(nav.iloc[-1]["total_equity"]) if not nav.empty else INITIAL_CAPITAL
    total_return = (final_equity / INITIAL_CAPITAL - 1) * 100

    # Total win rate
    total_wr = round(float((trades_df["net_pnl"] > 0).mean() * 100), 2) if not trades_df.empty else 0.0

    # ── Per-year stats ──
    annual = []
    running_equity = INITIAL_CAPITAL
    for yr in all_years:
        stats = _annual_stats(trades, yr, running_equity)
        annual.append(stats)
        running_equity = stats["year_end_equity"]

    # ── Strategy breakdown (total) ──
    if not trades_df.empty:
        grp = trades_df.groupby("strategy").agg(
            count=("net_pnl", "size"),
            total_pnl=("net_pnl", "sum"),
            win_rate=("net_pnl", lambda x: round((x > 0).mean() * 100, 1)),
            avg_pnl=("net_pnl", "mean"),
        ).to_dict("index")
        strat_breakdown = {k: {kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in grp.items()}
    else:
        strat_breakdown = {}

    # ── Save outputs ──
    trades_df.to_csv(TRADES_FILE, index=False, encoding="utf-8-sig")
    nav.to_csv(NAV_FILE, index=False, encoding="utf-8-sig")

    result = {
        "start_date": START_DATE,
        "end_date": END_DATE,
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return, 2),
        "total_trades": len(trades_df),
        "total_win_rate_pct": total_wr,
        "total_avg_pnl": round(float(trades_df["net_pnl"].mean()), 2) if not trades_df.empty else 0.0,
        "total_fees": round(float(trades_df["fees"].sum()), 2) if not trades_df.empty else 0.0,
        "strategy_breakdown": strat_breakdown,
        "annual": annual,
        "elapsed_seconds": round(elapsed_sec, 1),
    }
    RESULT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Print summary ──
    print()
    print("=" * 70)
    print("BASELINE ANNUAL BACKTEST RESULT")
    print("=" * 70)
    print(f"Period: {START_DATE} ~ {END_DATE}")
    print(f"Initial: {INITIAL_CAPITAL:,.0f}  Final: {final_equity:,.2f}")
    print(f"Total Return: {total_return:.2f}%  Trades: {len(trades_df)}  Win Rate: {total_wr:.1f}%")
    if not trades_df.empty:
        print(f"Total Fees: {trades_df['fees'].sum():,.2f}  Avg PnL: {trades_df['net_pnl'].mean():,.2f}")
    print()
    print("--- Per-Year ---")
    for a in annual:
        print(f"  {a['year']}: {a['return_pct']:+.2f}%  trades={a['trades']}  WR={a['win_rate_pct']:.1f}%  PnL={a['total_pnl']:+,.2f}  equity={a['year_end_equity']:,.2f}")
    print()
    print("--- Strategy Breakdown ---")
    for sname, sdata in strat_breakdown.items():
        print(f"  {sname}: {sdata['count']} trades  WR={sdata['win_rate']:.1f}%  PnL={sdata['total_pnl']:+,.2f}")
    print()
    print(f"Saved to: {RESULT_FILE}")
    print(f"Trades: {TRADES_FILE}")
    print(f"NAV: {NAV_FILE}")
    print(f"Elapsed: {elapsed_sec:.1f}s")

    _write_progress(f"[DONE] {total_return:.2f}% in {elapsed_sec:.1f}s")


if __name__ == "__main__":
    main()
