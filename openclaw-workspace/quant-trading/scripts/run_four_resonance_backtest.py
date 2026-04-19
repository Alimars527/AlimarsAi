#!/usr/bin/env python3
"""
四系统共振策略回测
通达信公式转Python — 均线+量能+MACD+KDJ 四系统共振

买入条件(四共振全满足):
  1. 均线共振: MA5>MA10>MA20>MA60 (多头排列)
  2. 量能共振: VOL>VOL5>VOL10 (量能放大)
  3. MACD共振: DIF>DEA 且 DIF>0 (多头动能)
  4. KDJ共振: K>D 且 J>50

卖出条件(四背离全满足):
  1. 均线背离: MA5<MA10<MA20<MA60 (空头排列)
  2. 量能萎缩: VOL<VOL5<VOL10
  3. MACD背离: DIF<DEA 且 DIF<0
  4. KDJ背离: K<D 且 J<50

框架: 5万起始, 2023-01~2026-04, T+1, 等权, 最多3仓, 最大持有30交易日
"""

from __future__ import annotations
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quant.sim_replay_common import (
    build_prepared_universe,
    load_trade_calendar,
    load_universe,
    safe_num,
)

DATA = ROOT / "data"
OUT = ROOT / "outputs"

START_DATE = "20230101"
END_DATE = "20260418"
INITIAL_CAPITAL = 50000.0
LOT_SIZE = 100
COMMISSION_RATE = 0.000086
MIN_COMMISSION = 5.0
STAMP_TAX_SELL = 0.0005
MAX_POSITIONS = 3
MAX_HOLD_DAYS = 30  # 安全阀：最多持有30个交易日

VERSION_TAG = "four_resonance_v2_loose_sell"
PROGRESS_PATH = OUT / f"sim_replay_{START_DATE}_{VERSION_TAG}_progress.json"


@dataclass
class Position:
    code: str
    name: str
    industry: str
    buy_date: str
    buy_price: float
    shares: int
    buy_idx: int = 0  # 在code_data中的行号，用于计算持仓天数
    initial_shares: int = 0


def _commission(amount: float) -> float:
    return max(amount * COMMISSION_RATE, MIN_COMMISSION)


def _buy_fee(price: float, shares: int) -> float:
    return _commission(price * shares)


def _sell_fee(price: float, shares: int) -> float:
    amount = price * shares
    return _commission(amount) + amount * STAMP_TAX_SELL


def add_resonance_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """为单只股票添加四系统共振所需的全部指标"""
    out = df.copy()
    C = safe_num(out['close'])
    V = safe_num(out['vol']).fillna(0.0)

    # ── 1. 均线系统 ──
    out['ma5'] = C.rolling(5).mean()
    out['ma10'] = C.rolling(10).mean()
    out['ma20'] = C.rolling(20).mean()
    out['ma60'] = C.rolling(60).mean()

    # ── 2. 量能系统 ──
    out['vol5'] = V.rolling(5).mean()
    out['vol10'] = V.rolling(10).mean()

    # ── 3. MACD系统 ──
    # indicators.py已算 macd_dif = EMA(C,12) - EMA(C,26)
    # 这里补算 DEA = EMA(DIF, 9)
    out['macd_dea'] = safe_num(out['macd_dif']).ewm(span=9, adjust=False).mean()

    # ── 4. KDJ系统 ──
    # indicators.py已算 kdj_k, kdj_d, kdj_j (与通达信SMA一致)

    return out


def check_buy_signal(row) -> bool:
    """买入共振: 四系统全满足"""
    try:
        # 均线共振: MA5>MA10>MA20>MA60
        ma5, ma10, ma20, ma60 = row['ma5'], row['ma10'], row['ma20'], row['ma60']
        if pd.isna(ma5) or pd.isna(ma10) or pd.isna(ma20) or pd.isna(ma60):
            return False
        ma_ok = ma5 > ma10 > ma20 > ma60

        # 量能共振: VOL>VOL5>VOL10
        vol = row['vol']
        vol5, vol10 = row['vol5'], row['vol10']
        if pd.isna(vol5) or pd.isna(vol10):
            return False
        vol_ok = vol > vol5 > vol10

        # MACD共振: DIF>DEA 且 DIF>0
        dif, dea = row['macd_dif'], row['macd_dea']
        if pd.isna(dif) or pd.isna(dea):
            return False
        macd_ok = dif > dea and dif > 0

        # KDJ共振: K>D 且 J>50
        k, d, j = row['kdj_k'], row['kdj_d'], row['kdj_j']
        if pd.isna(k) or pd.isna(d) or pd.isna(j):
            return False
        kdj_ok = k > d and j > 50

        return ma_ok and vol_ok and macd_ok and kdj_ok
    except Exception:
        return False


def check_sell_signal(row) -> bool:
    """卖出共振: 四背离全满足"""
    try:
        # 均线背离: MA5<MA10<MA20<MA60
        ma5, ma10, ma20, ma60 = row['ma5'], row['ma10'], row['ma20'], row['ma60']
        if pd.isna(ma5) or pd.isna(ma10) or pd.isna(ma20) or pd.isna(ma60):
            return False
        ma_bad = ma5 < ma10 < ma20 < ma60

        # 量能萎缩: VOL<VOL5<VOL10
        vol = row['vol']
        vol5, vol10 = row['vol5'], row['vol10']
        if pd.isna(vol5) or pd.isna(vol10):
            return False
        vol_bad = vol < vol5 < vol10

        # MACD背离: DIF<DEA 且 DIF<0
        dif, dea = row['macd_dif'], row['macd_dea']
        if pd.isna(dif) or pd.isna(dea):
            return False
        macd_bad = dif < dea and dif < 0

        # KDJ背离: K<D 且 J<50
        k, d, j = row['kdj_k'], row['kdj_d'], row['kdj_j']
        if pd.isna(k) or pd.isna(d) or pd.isna(j):
            return False
        kdj_bad = k < d and j < 50

        return ma_bad and vol_bad and macd_bad and kdj_bad
    except Exception:
        return False


def save_progress(status: str, processed: int = 0, total: int = 0, message: str = ""):
    pct = round(processed / total * 100, 2) if total else 0.0
    PROGRESS_PATH.write_text(json.dumps({
        "task": VERSION_TAG,
        "status": status,
        "processed": processed,
        "total": total,
        "progress_pct": pct,
        "updated_at": pd.Timestamp.now(tz='Asia/Shanghai').isoformat(),
        "message": message,
    }, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    cal = load_trade_calendar(START_DATE, END_DATE, DATA)
    cal_set = set(cal)
    meta = load_universe(DATA)

    print(f"[INFO] 加载universe: {len(meta)} 只股票")

    meta, code_data, code_idx, rotation_map = build_prepared_universe(
        START_DATE, END_DATE, DATA, min_rows=70,
    )

    print(f"[INFO] 可用股票: {len(code_data)}")

    # 为每只股票预计算共振指标
    print("[INFO] 计算共振指标...")
    for code in list(code_data.keys()):
        code_data[code] = add_resonance_indicators(code_data[code])

    if not code_data:
        raise RuntimeError("无可用股票")

    cash = INITIAL_CAPITAL
    positions: List[Position] = []
    trades = []
    nav_rows = []

    # 统计退出原因
    sell_resonance_count = 0
    max_hold_count = 0
    forced_close_count = 0

    save_progress("running", 0, len(cal), "starting")

    for td_i, td in enumerate(cal):
        # =============================================
        # 1) 检查卖出/到期 → 平仓
        # =============================================
        remain_positions = []
        for p in positions:
            idx_map = code_idx.get(p.code, {})
            if td not in idx_map:
                remain_positions.append(p)
                continue

            cur_idx = idx_map[td]
            df = code_data[p.code]
            row = df.iloc[cur_idx]
            held_days = cur_idx - p.buy_idx  # 交易日天数

            sell_this = False
            exit_reason = ""

            # 优先级1: 卖出共振
            if check_sell_signal(row):
                sell_price = float(row['close'])
                exit_reason = "sell_resonance"
                sell_resonance_count += 1
                sell_this = True

            # 优先级2: 最大持有天数到期
            elif held_days >= MAX_HOLD_DAYS:
                sell_price = float(row['close'])
                exit_reason = "max_hold"
                max_hold_count += 1
                sell_this = True

            if sell_this:
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                net_pnl = proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares)
                trades.append({
                    "code": p.code, "name": p.name, "industry": p.industry,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4),
                    "sell_price": round(sell_price, 4),
                    "shares": p.shares,
                    "held_days": held_days,
                    "gross_pnl": round((sell_price - p.buy_price) * p.shares, 4),
                    "fees": round(_buy_fee(p.buy_price, p.initial_shares) + fee, 4),
                    "net_pnl": round(net_pnl, 4),
                    "exit_reason": exit_reason,
                })
                continue

            remain_positions.append(p)

        positions = remain_positions

        # =============================================
        # 2) 检查买入信号 → 次日开盘买入
        # =============================================
        free_slots = max(0, MAX_POSITIONS - len(positions))
        held_codes = {p.code for p in positions}

        sigs = []
        if free_slots > 0:
            for r in meta.itertuples(index=False):
                code = r.ts_code
                if code not in code_data:
                    continue
                idx_map = code_idx[code]
                if td not in idx_map:
                    continue

                idx = idx_map[td]
                df = code_data[code]
                if idx + 1 >= len(df):
                    continue

                # 跳过已持仓
                if code in held_codes:
                    continue

                row = df.iloc[idx]
                next_row = df.iloc[idx + 1]
                next_date = str(next_row['trade_date'])
                if next_date not in cal_set:
                    continue

                if check_buy_signal(row):
                    sigs.append({
                        "code": code, "name": r.name, "industry": r.industry,
                        "signal_date": td,
                        "next_date": next_date,
                        "next_open": float(next_row['open']),
                        "next_low": float(next_row['low']),
                        "kdj_j": float(row['kdj_j']) if pd.notna(row.get('kdj_j')) else 999,
                        "next_idx": idx + 1,
                    })

        # 按J值升序排列（刚从低位起来优先）
        if free_slots > 0 and sigs:
            sigs.sort(key=lambda s: s['kdj_j'])
            selected = sigs[:free_slots * 3]

            opened = 0
            for s in selected:
                if opened >= free_slots:
                    break

                buy_price = s['next_open']
                if buy_price <= 0:
                    continue

                # 等权
                budget = cash / max(1, free_slots - opened)
                shares = int(budget // buy_price // LOT_SIZE) * LOT_SIZE
                if shares <= 0:
                    continue

                fee = _buy_fee(buy_price, shares)
                cost = buy_price * shares + fee
                if cost > cash:
                    continue

                cash -= cost
                positions.append(Position(
                    code=s['code'], name=s['name'], industry=s['industry'],
                    buy_date=s['next_date'], buy_price=buy_price,
                    shares=shares, buy_idx=s['next_idx'],
                    initial_shares=shares,
                ))
                opened += 1

        # =============================================
        # 3) 记录净值
        # =============================================
        mv = 0.0
        for p in positions:
            idx_map = code_idx.get(p.code, {})
            if td in idx_map:
                px = float(code_data[p.code].iloc[idx_map[td]]['close'])
                mv += px * p.shares
            else:
                mv += p.buy_price * p.shares

        processed = td_i + 1
        if processed % 20 == 0 or processed == len(cal):
            save_progress("running", processed, len(cal), f"processing {td}")

        nav_rows.append({
            "trade_date": td,
            "cash": round(cash, 2),
            "market_value": round(mv, 2),
            "total_equity": round(cash + mv, 2),
            "positions": len(positions),
        })

    # =============================================
    # 4) 强制平仓剩余持仓
    # =============================================
    last_td = cal[-1]
    for p in positions:
        idx_map = code_idx.get(p.code, {})
        sell_price = p.buy_price
        if last_td in idx_map:
            sell_price = float(code_data[p.code].iloc[idx_map[last_td]]['close'])
        fee = _sell_fee(sell_price, p.shares)
        proceeds = sell_price * p.shares - fee
        cash += proceeds
        net_pnl = proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares)
        forced_close_count += 1
        trades.append({
            "code": p.code, "name": p.name, "industry": p.industry,
            "buy_date": p.buy_date, "sell_date": f"{last_td}_FORCED",
            "buy_price": round(p.buy_price, 4),
            "sell_price": round(sell_price, 4),
            "shares": p.shares,
            "held_days": 0,
            "gross_pnl": round((sell_price - p.buy_price) * p.shares, 4),
            "fees": round(_buy_fee(p.buy_price, p.initial_shares) + fee, 4),
            "net_pnl": round(net_pnl, 4),
            "exit_reason": "forced_close",
        })

    # =============================================
    # 5) 统计结果
    # =============================================
    nav = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)

    final_equity = cash
    total_return = (final_equity / INITIAL_CAPITAL - 1) * 100

    eq = nav["total_equity"].values
    peak = np.maximum.accumulate(eq)
    drawdown = (eq - peak) / peak * 100
    max_dd = float(drawdown.min())

    years = (pd.Timestamp(END_DATE) - pd.Timestamp(START_DATE)).days / 365.25
    cagr = ((final_equity / INITIAL_CAPITAL) ** (1 / years) - 1) * 100 if years > 0 else 0

    win_rate = round(float((trades_df["net_pnl"] > 0).mean() * 100), 2) if not trades_df.empty else 0.0

    # 退出原因统计
    exit_stats = {}
    if not trades_df.empty:
        exit_stats = trades_df.groupby("exit_reason").agg(
            count=("exit_reason", "size"),
            avg_pnl=("net_pnl", "mean"),
            total_pnl=("net_pnl", "sum"),
            win_rate=("net_pnl", lambda x: (x > 0).mean() * 100),
        ).to_dict(orient="index")

    # 分年统计
    yearly = {}
    if not trades_df.empty:
        trades_df["sell_year"] = trades_df["sell_date"].str[:4]
        for yr, grp in trades_df.groupby("sell_year"):
            yearly[yr] = {
                "count": int(len(grp)),
                "win_rate": round(float((grp["net_pnl"] > 0).mean() * 100), 2),
                "total_pnl": round(float(grp["net_pnl"].sum()), 2),
            }

    # 持仓天数统计
    avg_hold = 0
    median_hold = 0
    if not trades_df.empty and 'held_days' in trades_df.columns:
        valid_holds = trades_df[trades_df['held_days'] > 0]['held_days']
        if not valid_holds.empty:
            avg_hold = round(float(valid_holds.mean()), 1)
            median_hold = round(float(valid_holds.median()), 1)

    summary = {
        "version": VERSION_TAG,
        "strategy": "四系统共振(均线+量能+MACD+KDJ)",
        "start_date": START_DATE,
        "end_date": END_DATE,
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "trade_count": int(len(trades_df)),
        "win_rate_pct": win_rate,
        "cagr_pct": round(cagr, 2),
        "avg_hold_days": avg_hold,
        "median_hold_days": median_hold,
        "max_positions": MAX_POSITIONS,
        "max_hold_days": MAX_HOLD_DAYS,
        "exit_counts": {
            "sell_resonance": sell_resonance_count,
            "max_hold": max_hold_count,
            "forced_close": forced_close_count,
        },
        "exit_stats": exit_stats,
        "yearly_breakdown": yearly,
        "baseline_ref": "+219.99% / 585笔 / 50.6%WR / -16.16%DD",
        "nav_path": str(OUT / f"sim_replay_{START_DATE}_{VERSION_TAG}_nav.csv"),
        "trades_path": str(OUT / f"sim_replay_{START_DATE}_{VERSION_TAG}_trades.csv"),
    }

    nav.to_csv(OUT / f"sim_replay_{START_DATE}_{VERSION_TAG}_nav.csv", index=False, encoding="utf-8-sig")
    trades_df.to_csv(OUT / f"sim_replay_{START_DATE}_{VERSION_TAG}_trades.csv", index=False, encoding="utf-8-sig")
    (OUT / f"sim_replay_{START_DATE}_{VERSION_TAG}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    save_progress("done", len(cal), len(cal), "finished")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    try:
        PROGRESS_PATH.unlink()
    except Exception:
        pass


if __name__ == "__main__":
    main()
