#!/usr/bin/env python3
"""
通达信三个公式回测的公共引擎
买入规则：公式出买点 且 (当日或前1日有B1或砖型图信号) → 当日收盘价买入
卖出规则：+10%卖一半，+20%全卖，砖型图转绿全卖
"""
from __future__ import annotations
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Callable

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

# ── 回测参数 ──────────────────────────────────────
START_DATE = "20230101"
END_DATE = "20260403"
INITIAL_CAPITAL = 50000.0
LOT_SIZE = 100
COMMISSION_RATE = 0.000086
MIN_COMMISSION = 5.0
STAMP_TAX_SELL = 0.0005
MAX_POSITIONS = 5          # 最大持仓数
BUDGET_PER_TRADE = 10000.0 # 每笔固定金额

B1_TP1 = 0.10
B1_TP2 = 0.20


@dataclass
class Position:
    code: str
    name: str
    industry: str
    strategy: str
    buy_date: str
    buy_price: float
    shares: int
    initial_shares: int
    tp1_done: bool = False
    tp2_done: bool = False


def _commission(amount: float) -> float:
    return max(amount * COMMISSION_RATE, MIN_COMMISSION)


def _buy_fee(price: float, shares: int) -> float:
    return _commission(price * shares)


def _sell_fee(price: float, shares: int) -> float:
    amount = price * shares
    return _commission(amount) + amount * STAMP_TAX_SELL


def _sma_cn(series: pd.Series, n: int, m: int) -> pd.Series:
    """通达信SMA: SMA(X,N,M) = M*X+(N-M)*SMA[上一周期]/N"""
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
    """复用 baseline v6 的 B1 信号判断"""
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


def brick_signal_ok(df: pd.DataFrame, idx: int, industry: str, rotation_map: dict) -> bool:
    """砖型图信号判断（简化版，不重复计算rotation，直接用rotation_map）"""
    if df is None or df.empty or idx < 4:
        return False
    latest = df.iloc[idx]
    white = safe_num(latest.get('white_line'))
    yellow = safe_num(latest.get('yellow_line'))
    high = safe_num(latest.get('high'))
    if pd.isna(white) or pd.isna(yellow) or pd.isna(high):
        return False
    if not (high >= white and white > yellow):
        return False
    if not bool(latest.get('brick_raw_turn_red', False)) or not bool(latest.get('brick_history_ok', False)):
        return False
    if 'brick_formula_value' not in df.columns or 'brick_formula_green' not in df.columns:
        return False
    z = safe_num(df['brick_formula_value']).fillna(0)
    green = df['brick_formula_green'].fillna(False).astype(bool)
    if not bool(green.iloc[idx - 1] and green.iloc[idx - 2] and green.iloc[idx - 3] and green.iloc[idx - 4]):
        return False
    if not bool(z.iloc[idx - 4] > z.iloc[idx - 3] > z.iloc[idx - 2] > z.iloc[idx - 1]):
        return False
    if not bool(z.iloc[idx] >= z.iloc[idx - 1]):
        return False
    td = str(latest.get('trade_date', ''))
    if not rotation_map.get((td, industry), False):
        return False
    return True


def has_b1_or_brick(df: pd.DataFrame, idx: int, industry: str, rotation_map: dict) -> tuple[bool, bool, bool, bool]:
    """检查当日和前1日是否有B1或砖型图信号。返回 (当日B1, 当日Brick, 前1日B1, 前1日Brick)"""
    today_b1 = b1_experimental_ok(df, idx)
    today_brick = brick_signal_ok(df, idx, industry, rotation_map)
    prev_b1 = False
    prev_brick = False
    if idx >= 1:
        prev_b1 = b1_experimental_ok(df, idx - 1)
        prev_brick = brick_signal_ok(df, idx - 1, industry, rotation_map)
    return today_b1, today_brick, prev_b1, prev_brick


def run_backtest(
    version_tag: str,
    buy_signal_fn: Callable[[pd.DataFrame, int], bool],
    strategy_name: str = "formula",
):
    """
    通用回测引擎
    buy_signal_fn(df, idx) -> bool: 当日是否出买点信号
    """
    OUT.mkdir(parents=True, exist_ok=True)

    cal = load_trade_calendar(START_DATE, END_DATE, DATA)
    cal_set = set(cal)

    meta = load_universe(DATA)
    print(f"[{version_tag}] preparing universe: {len(meta)}")
    meta, code_data, code_idx, rotation_map = build_prepared_universe(
        START_DATE, END_DATE, DATA, min_rows=40,
    )
    print(f"[{version_tag}] usable codes: {len(code_data)}")

    cash = INITIAL_CAPITAL
    positions: List[Position] = []
    trades = []
    nav_rows = []

    tp1_count = 0
    tp2_count = 0
    brick_green_count = 0

    for td in cal:
        # ── 1) 处理平仓 ──
        remain_positions = []
        for p in positions:
            idx_map = code_idx.get(p.code, {})
            if td not in idx_map:
                remain_positions.append(p)
                continue
            idx = idx_map[td]
            df = code_data[p.code]
            row = df.iloc[idx]
            high = float(row["high"])
            close = float(row["close"])
            low = float(row["low"])

            # TP2: +20% 全卖（盘中high触及）
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

            # TP1: +10% 卖一半（盘中high触及）
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
                if p.shares <= 0:
                    continue

            # 砖型图转绿：全卖（当日收盘确认，次日执行？不，当日收盘即可确认，当日收盘价卖出）
            is_green = bool(row.get("brick_formula_green", False))
            if is_green:
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
                    "exit_reason": "brick_green",
                })
                brick_green_count += 1
                continue

            remain_positions.append(p)

        positions = remain_positions

        # ── 2) 生成信号 & 开仓 ──
        if len(positions) >= MAX_POSITIONS:
            # 只更新NAV
            mtm = cash
            for p in positions:
                if p.code in code_data and td in code_idx.get(p.code, {}):
                    mtm += p.shares * float(code_data[p.code].iloc[code_idx[p.code][td]]["close"])
            nav_rows.append({"date": td, "nav": round(mtm, 2), "cash": round(cash, 2)})
            continue

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

            # 先检查公式买点信号
            if not buy_signal_fn(df, idx):
                continue

            # 再检查 B1/砖型图 辅助确认
            today_b1, today_brick, prev_b1, prev_brick = has_b1_or_brick(df, idx, r.industry, rotation_map)
            if not (today_b1 or today_brick or prev_b1 or prev_brick):
                continue

            row = df.iloc[idx]
            sigs.append({
                "code": code, "name": r.name, "industry": r.industry,
                "signal_date": td,
                "signal_close": float(row["close"]),
                "today_b1": today_b1, "today_brick": today_brick,
                "prev_b1": prev_b1, "prev_brick": prev_brick,
            })

        # 开仓（简单按发现顺序，每只分配 BUDGET_PER_TRADE）
        for s in sigs:
            if len(positions) >= MAX_POSITIONS:
                break
            if cash < BUDGET_PER_TRADE:
                break

            buy_price = s["signal_close"]
            shares = int(BUDGET_PER_TRADE // buy_price // LOT_SIZE) * LOT_SIZE
            if shares <= 0:
                continue

            fee = _buy_fee(buy_price, shares)
            cost = buy_price * shares + fee
            if cost > cash:
                continue

            cash -= cost
            positions.append(Position(
                code=s["code"], name=s["name"], industry=s["industry"],
                strategy=strategy_name,
                buy_date=td, buy_price=buy_price,
                shares=shares, initial_shares=shares,
            ))
            trades.append({
                "code": s["code"], "name": s["name"], "industry": s["industry"],
                "strategy": strategy_name,
                "buy_date": td, "sell_date": "",
                "buy_price": round(buy_price, 4), "sell_price": 0.0,
                "shares": shares,
                "gross_pnl": 0.0, "fees": round(fee, 4), "net_pnl": round(-fee, 4),
                "exit_reason": "open",
            })

        # ── NAV ──
        mtm = cash
        for p in positions:
            if p.code in code_data and td in code_idx.get(p.code, {}):
                mtm += p.shares * float(code_data[p.code].iloc[code_idx[p.code][td]]["close"])
        nav_rows.append({"date": td, "nav": round(mtm, 2), "cash": round(cash, 2)})

    # ── 3) 统计 ──
    closed_trades = [t for t in trades if t["exit_reason"] != "open"]
    if not closed_trades:
        print(f"[{version_tag}] 无交易")
        return

    gross_pnls = [t["gross_pnl"] for t in closed_trades]
    net_pnls = [t["net_pnl"] for t in closed_trades]
    wins = [p for p in net_pnls if p > 0]
    losses = [p for p in net_pnls if p <= 0]

    total_gross = sum(gross_pnls)
    total_net = sum(net_pnls)
    win_rate = len(wins) / len(closed_trades) * 100 if closed_trades else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float('inf')

    nav_df = pd.DataFrame(nav_rows)
    nav_df["nav"] = safe_num(nav_df["nav"])
    peak = nav_df["nav"].cummax()
    dd = (nav_df["nav"] - peak) / peak
    max_dd = dd.min() * 100
    final_nav = nav_df["nav"].iloc[-1] if not nav_df.empty else INITIAL_CAPITAL
    total_return = (final_nav - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    # 按年统计
    nav_df["year"] = nav_df["date"].str[:4]
    year_stats = []
    for y, g in nav_df.groupby("year"):
        if len(g) >= 2:
            y_ret = (g["nav"].iloc[-1] - g["nav"].iloc[0]) / g["nav"].iloc[0] * 100
            year_stats.append({"year": y, "return_pct": round(y_ret, 2)})

    # 退出原因统计
    exit_reasons = {}
    for t in closed_trades:
        r = t["exit_reason"]
        exit_reasons[r] = exit_reasons.get(r, 0) + 1

    summary = {
        "version": version_tag,
        "period": f"{START_DATE} ~ {END_DATE}",
        "initial_capital": INITIAL_CAPITAL,
        "budget_per_trade": BUDGET_PER_TRADE,
        "max_positions": MAX_POSITIONS,
        "total_trades": len(closed_trades),
        "total_return_pct": round(total_return, 2),
        "final_nav": round(final_nav, 2),
        "win_rate": round(win_rate, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "tp1_count": tp1_count,
        "tp2_count": tp2_count,
        "brick_green_count": brick_green_count,
        "exit_reasons": exit_reasons,
        "year_breakdown": year_stats,
    }

    print(f"\n========== {version_tag} 回测结果 ==========")
    print(f"总收益: {total_return:+.2f}%  终值: ¥{final_nav:,.2f}")
    print(f"交易笔数: {len(closed_trades)}  胜率: {win_rate:.1f}%")
    print(f"盈亏比: {profit_factor:.2f}  均盈: ¥{avg_win:,.2f}  均亏: ¥{avg_loss:,.2f}")
    print(f"最大回撤: {max_dd:.2f}%")
    print(f"TP1(半仓): {tp1_count}  TP2(全仓): {tp2_count}  砖绿清仓: {brick_green_count}")
    print(f"退出分布: {exit_reasons}")
    for ys in year_stats:
        print(f"  {ys['year']}年: {ys['return_pct']:+.2f}%")
    print("=" * 50)

    # 保存结果
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"tdx_{version_tag}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pd.DataFrame(closed_trades).to_csv(OUT / f"tdx_{version_tag}_trades.csv", index=False, encoding="utf-8-sig")
    nav_df.to_csv(OUT / f"tdx_{version_tag}_nav.csv", index=False, encoding="utf-8-sig")
    print(f"[{version_tag}] 结果已保存到 outputs/")
