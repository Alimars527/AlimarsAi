#!/usr/bin/env python3
"""
Candlestick Pattern Backtest — 9 Bullish Pattern Groups
========================================================
Unified rules for fair cross-pattern comparison:
  Buy:   Signal day T → buy at T+1 open
  Sell:  Hold 5 trading days → sell at close (T+5)
  Pos:   Equal weight, max 3 concurrent positions
  Period: 2023-01 ~ 2026-04, 50K starting capital

Usage:
  PYTHONPATH=. python3 scripts/run_candle_pattern_backtest.py
"""
import sys
import time
import json
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quant.sim_replay_common import (
    build_prepared_universe, load_trade_calendar, V4_EXCLUDED_INDUSTRIES,
)
from quant.candlestick_patterns import add_candlestick_patterns, PATTERN_GROUPS

# ── Config ──────────────────────────────────────────────
START = "20230101"
END   = "20260403"   # match existing cache
CAPITAL0 = 50_000
MAX_POS  = 3
HOLD     = 5         # hold N trading days
OUT_DIR  = ROOT / "outputs"


# ── Signal Collection ──────────────────────────────────
def collect_signals(pattern_cols, code_data, code_idx, trade_cal):
    """Collect all valid (signal_date, code, entry/exit prices) for a group."""
    cal_idx = {d: i for i, d in enumerate(trade_cal)}
    signals = []

    for code, df in code_data.items():
        idx_map = code_idx.get(code, {})
        # OR mask across all pattern columns in this group
        mask = df[pattern_cols[0]].fillna(False).astype(bool)
        for col in pattern_cols[1:]:
            mask |= df[col].fillna(False).astype(bool)

        for ri in np.where(mask)[0]:
            sig_date = df.iloc[ri]["trade_date"]
            if sig_date not in cal_idx:
                continue
            si = cal_idx[sig_date]
            # Entry: T+1 open
            ei = si + 1
            # Exit: T+1+HOLD close  (hold HOLD trading days from entry)
            xi = ei + HOLD
            if ei >= len(trade_cal):
                continue
            if xi >= len(trade_cal):
                xi = len(trade_cal) - 1

            entry_date = trade_cal[ei]
            exit_date  = trade_cal[xi]

            row_e = idx_map.get(entry_date)
            row_x = idx_map.get(exit_date)
            if row_e is None or row_x is None:
                continue

            ep = float(df.iloc[row_e]["open"])
            xp = float(df.iloc[row_x]["close"])
            if ep <= 0:
                continue

            signals.append({
                "code": code, "sig_date": sig_date,
                "entry_date": entry_date, "exit_date": exit_date,
                "entry_price": ep, "exit_price": xp,
            })

    return signals


# ── Portfolio Simulation ───────────────────────────────
def simulate(signals, trade_cal):
    """Simulate portfolio: max MAX_POS concurrent positions, equal weight."""
    if not signals:
        return None

    by_entry = defaultdict(list)
    for s in signals:
        by_entry[s["entry_date"]].append(s)

    cash = float(CAPITAL0)
    positions = {}   # code → {entry_date, exit_date, entry_price, exit_price, shares}
    trades = []
    cum_pnl = 0.0
    peak_pnl = 0.0
    max_dd = 0.0

    for today in trade_cal:
        # 1. Close positions that mature today
        to_close = [c for c in positions if positions[c]["exit_date"] == today]
        for code in to_close:
            p = positions.pop(code)
            pnl = (p["exit_price"] - p["entry_price"]) * p["shares"]
            cash += p["exit_price"] * p["shares"]
            cum_pnl += pnl
            trades.append({
                "code": code,
                "entry_date": p["entry_date"],
                "exit_date": today,
                "entry_price": p["entry_price"],
                "exit_price": p["exit_price"],
                "shares": p["shares"],
                "pnl": round(pnl, 2),
                "ret_pct": round((p["exit_price"] / p["entry_price"] - 1) * 100, 4),
            })

        # 2. Open new positions
        if today in by_entry:
            for sig in by_entry[today]:
                if len(positions) >= MAX_POS:
                    break
                if sig["code"] in positions:
                    continue
                slots_left = MAX_POS - len(positions)
                alloc = cash / slots_left
                shares = int(alloc / sig["entry_price"] / 100) * 100
                if shares <= 0:
                    continue
                cost = shares * sig["entry_price"]
                if cost > cash:
                    shares = int(cash / sig["entry_price"] / 100) * 100
                    if shares <= 0:
                        continue
                    cost = shares * sig["entry_price"]
                cash -= cost
                positions[sig["code"]] = {
                    "entry_date": sig["entry_date"],
                    "exit_date": sig["exit_date"],
                    "entry_price": sig["entry_price"],
                    "exit_price": sig["exit_price"],
                    "shares": shares,
                }

        # 3. Drawdown tracking (realized PnL based)
        if cum_pnl > peak_pnl:
            peak_pnl = cum_pnl
        dd = (peak_pnl - cum_pnl) / CAPITAL0 * 100
        if dd > max_dd:
            max_dd = dd

    # Force-close remaining at end
    for code in list(positions):
        p = positions.pop(code)
        pnl = (p["exit_price"] - p["entry_price"]) * p["shares"]
        cash += p["exit_price"] * p["shares"]
        cum_pnl += pnl
        trades.append({
            "code": code,
            "entry_date": p["entry_date"],
            "exit_date": p["exit_date"],
            "entry_price": p["entry_price"],
            "exit_price": p["exit_price"],
            "shares": p["shares"],
            "pnl": round(pnl, 2),
            "ret_pct": round((p["exit_price"] / p["entry_price"] - 1) * 100, 4),
        })

    return _compile_stats(trades, n_signals=len(signals), cash=cash,
                          cum_pnl=cum_pnl, max_dd=max_dd)


def _compile_stats(trades, n_signals, cash, cum_pnl, max_dd):
    """Compute summary statistics from trade list."""
    n = len(trades)
    if n == 0:
        return None
    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] <= 0)
    avg_win  = np.mean([t["ret_pct"] for t in trades if t["pnl"] > 0]) if wins else 0
    avg_loss = np.mean([t["ret_pct"] for t in trades if t["pnl"] <= 0]) if losses else 0
    total_ret = (cash - CAPITAL0) / CAPITAL0 * 100

    return {
        "n_signals": n_signals,
        "n_trades": n,
        "win_rate": round(wins / n * 100, 1),
        "avg_return": round(np.mean([t["ret_pct"] for t in trades]), 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "total_return": round(total_ret, 2),
        "max_dd": round(max_dd, 2),
        "final_capital": round(cash, 0),
        "trades": trades,
    }


# ── Main ───────────────────────────────────────────────
def main():
    print("=" * 70)
    print("蜡烛图形态回测 — 9组看涨形态")
    print(f"周期: {START}~{END}  起始资金: {CAPITAL0:,}  最大持仓: {MAX_POS}  持有: {HOLD}天")
    print("=" * 70)

    # ── Step 1: Load universe (cached) ──
    print("\n[1/3] 加载股票池...")
    t0 = time.time()
    meta, code_data, code_idx, _ = build_prepared_universe(
        START, END, excluded_industries=V4_EXCLUDED_INDUSTRIES,
    )
    print(f"      {len(code_data)} 只股票, {time.time()-t0:.1f}s")

    # ── Step 2: Add candlestick patterns ──
    print("\n[2/3] 计算蜡烛图形态...")
    t0 = time.time()
    for code in code_data:
        code_data[code] = add_candlestick_patterns(code_data[code])
    print(f"      完成, {time.time()-t0:.1f}s")

    # ── Step 3: Run each pattern group ──
    trade_cal = load_trade_calendar(START, END)
    print(f"\n[3/3] 回测9组形态 ({len(trade_cal)} 交易日)...")

    all_results = []
    for i, (name, cols) in enumerate(PATTERN_GROUPS.items(), 1):
        t1 = time.time()
        signals = collect_signals(cols, code_data, code_idx, trade_cal)
        result = simulate(signals, trade_cal)

        if result is None:
            print(f"  [{i}/9] {name}: {len(signals)} 信号 → 无有效交易")
            all_results.append({"pattern": name, "n_signals": len(signals), "n_trades": 0})
            continue

        result["pattern"] = name
        all_results.append(result)
        print(f"  [{i}/9] {name}: {result['n_signals']}信号 → {result['n_trades']}笔  "
              f"WR={result['win_rate']:.1f}%  均收={result['avg_return']:.2f}%  "
              f"总收={result['total_return']:.2f}%  DD={result['max_dd']:.2f}%  "
              f"({time.time()-t1:.1f}s)")

    # ── Summary ──
    print("\n" + "=" * 90)
    print(f"{'形态':<10} {'信号':>6} {'交易':>6} {'胜率%':>6} {'均收%':>7} "
          f"{'均赢%':>7} {'均亏%':>7} {'总收%':>9} {'DD%':>7}")
    print("-" * 90)
    for r in all_results:
        if r["n_trades"] == 0:
            print(f"{r['pattern']:<10} {r['n_signals']:>6} {'--':>6}")
        else:
            print(f"{r['pattern']:<10} {r['n_signals']:>6} {r['n_trades']:>6} "
                  f"{r['win_rate']:>6.1f} {r['avg_return']:>7.2f} "
                  f"{r['avg_win']:>7.2f} {r['avg_loss']:>7.2f} "
                  f"{r['total_return']:>9.2f} {r['max_dd']:>7.2f}")
    print("=" * 90)

    # ── Save ──
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = []
    for r in all_results:
        s = {k: v for k, v in r.items() if k != "trades"}
        summary.append(s)

    out_json = OUT_DIR / f"candle_summary_{START}_{END}.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n摘要已保存: {out_json}")

    # Save per-pattern trades
    for r in all_results:
        if "trades" not in r:
            continue
        name_safe = r["pattern"]
        trades_df = pd.DataFrame(r["trades"])
        out_csv = OUT_DIR / f"candle_trades_{name_safe}_{START}_{END}.csv"
        trades_df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print("逐笔交易已保存: outputs/candle_trades_*")


if __name__ == "__main__":
    main()
