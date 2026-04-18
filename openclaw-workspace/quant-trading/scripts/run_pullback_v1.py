#!/usr/bin/env python3
"""
缩量回调低吸策略 V1 回测
5万起始, 2023-01-01 ~ 2026-04-03
与BaseLine互补的独立策略: 抓上涨中继回调止跌

买入条件: 趋势确认(MA多头) + 缩量回调至支撑 + 止跌蜡烛图信号
卖出条件: TP1(+8%卖半) / TP2(+15%全走) / MA20破位 / 8天时间止损 / -5%硬止损 / 回撤止损
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
END_DATE = "20260403"
INITIAL_CAPITAL = 50000.0
LOT_SIZE = 100
COMMISSION_RATE = 0.000086
MIN_COMMISSION = 5.0
STAMP_TAX_SELL = 0.0005

# 策略参数
TP1_PCT = 0.08       # +8% 卖半仓
TP2_PCT = 0.15       # +15% 全走
MAX_HOLD_DAYS = 8    # 时间止损
HARD_STOP_PCT = -0.05  # -5% 硬止损
TRAILING_SL_PCT = 0.03  # TP1后回撤止损幅度
MAX_POSITIONS = 3     # 最多同时持有
MAX_NEW_PER_DAY = 1   # 每日最多新开
POSITION_PCT = 0.30   # 单票仓位比例

VOL_SHRINK_RATIO = 0.8   # 缩量比(当日量 < 5日均量 × 此值)
MA_SUPPORT_TOLERANCE_M10 = 0.02  # 距MA10容差2%
MA_SUPPORT_TOLERANCE_M20 = 0.03  # 距MA20容差3%

VERSION_TAG = "pullback_v1"


@dataclass
class Position:
    code: str
    name: str
    industry: str
    buy_date: str
    buy_price: float
    shares: int
    initial_shares: int = 0
    tp1_done: bool = False
    trailing_stop_price: float = 0.0


def _commission(amount: float) -> float:
    return max(amount * COMMISSION_RATE, MIN_COMMISSION)


def _buy_fee(price: float, shares: int) -> float:
    return _commission(price * shares)


def _sell_fee(price: float, shares: int) -> float:
    amount = price * shares
    return _commission(amount) + amount * STAMP_TAX_SELL


def compute_ma(df: pd.DataFrame, col: str = "close", n: int = 5) -> pd.Series:
    return safe_num(df[col]).rolling(n).mean()


def detect_hammer(open_s: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """锤子线: 下影线 >= 实体2倍, 上影线 < 实体"""
    body = (close - open_s).abs()
    body = body.replace(0, 0.001)
    lower_shadow = open_s.combine(close, min) - low
    upper_shadow = high - open_s.combine(close, max)
    return (lower_shadow >= body * 2) & (upper_shadow < body)


def detect_bullish_engulf(open_s: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """看涨吞没: 当日阳线实体完全包住前一日阴线实体"""
    prev_open = open_s.shift(1)
    prev_close = close.shift(1)
    today_yang = close > open_s
    prev_yin = prev_close < prev_open
    engulf = (open_s <= prev_close) & (close >= prev_open)
    return today_yang & prev_yin & engulf


def detect_doji(open_s: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """十字星: 实体占全幅 < 15%"""
    full_range = high - low
    full_range = full_range.replace(0, 0.001)
    body = (close - open_s).abs()
    return (body / full_range) < 0.15


def detect_piercing(open_s: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """刺透形态: 前日阴线, 当日开盘低于前日收盘(=前日开盘下方), 收盘高于前日 midpoint"""
    prev_open = open_s.shift(1)
    prev_close = close.shift(1)
    prev_mid = (prev_open + prev_close) / 2
    prev_yin = prev_close < prev_open
    gap_down = open_s < prev_close
    pierce_up = close > prev_mid
    return prev_yin & gap_down & pierce_up


def check_pullback_signal(df: pd.DataFrame, idx: int) -> Optional[dict]:
    """检查idx位置是否满足缩量回调低吸的全部买入条件"""
    if idx < 25:
        return None

    sub = df.iloc[:idx + 1].copy().reset_index(drop=True)
    n = len(sub)
    if n < 25:
        return None

    C = safe_num(sub['close'])
    O = safe_num(sub['open'])
    H = safe_num(sub['high'])
    L = safe_num(sub['low'])
    VOL = safe_num(sub['vol']).fillna(0.0)

    # === 2.1 趋势确认 ===
    ma5 = C.rolling(5).mean()
    ma10 = C.rolling(10).mean()
    ma20 = C.rolling(20).mean()

    last_close = float(C.iloc[-1])
    last_ma5 = float(ma5.iloc[-1])
    last_ma10 = float(ma10.iloc[-1])
    last_ma20 = float(ma20.iloc[-1])

    if pd.isna(last_ma20):
        return None

    # MA5 > MA10 > MA20 多头排列
    if not (last_ma5 > last_ma10 > last_ma20):
        return None

    # 收盘价在MA20之上
    if last_close < last_ma20:
        return None

    # MA20斜率 > 0 (5日内MA20上升)
    ma20_slope = float(ma20.iloc[-1]) - float(ma20.iloc[-6]) if n >= 6 else 0
    if ma20_slope <= 0:
        return None

    # === 2.2 回调特征 ===
    # 近5日内至少有1日收盘价低于MA5
    recent_5_below_ma5 = False
    for i in range(max(0, n - 5), n):
        if pd.notna(ma5.iloc[i]) and float(C.iloc[i]) < float(ma5.iloc[i]):
            recent_5_below_ma5 = True
            break
    if not recent_5_below_ma5:
        return None

    # 当日收盘价在MA10或MA20附近
    dist_ma10 = abs(last_close - last_ma10) / last_ma10 if last_ma10 > 0 else 999
    dist_ma20 = abs(last_close - last_ma20) / last_ma20 if last_ma20 > 0 else 999
    near_ma10 = dist_ma10 <= MA_SUPPORT_TOLERANCE_M10
    near_ma20 = dist_ma20 <= MA_SUPPORT_TOLERANCE_M20
    if not (near_ma10 or near_ma20):
        return None

    # === 2.3 缩量确认 ===
    vol_today = float(VOL.iloc[-1])
    vol_avg5 = float(VOL.iloc[-5:].mean()) if n >= 5 else 0
    if vol_avg5 <= 0:
        return None
    if vol_today >= vol_avg5 * VOL_SHRINK_RATIO:
        return None

    # 近3日成交量递减
    if n < 3:
        return None
    v3 = float(VOL.iloc[-3])
    v2 = float(VOL.iloc[-2])
    v1 = float(VOL.iloc[-1])
    if not (v3 > v2 > v1):
        return None

    # === 2.4 止跌信号 ===
    hammer = detect_hammer(O, H, L, C)
    engulf = detect_bullish_engulf(O, H, L, C)
    doji = detect_doji(O, H, L, C)
    pierce = detect_piercing(O, H, L, C)

    signal_type = []
    if bool(hammer.iloc[-1]):
        signal_type.append("锤子线")
    if bool(engulf.iloc[-1]):
        signal_type.append("看涨吞没")
    if bool(doji.iloc[-1]):
        signal_type.append("十字星")
    if bool(pierce.iloc[-1]):
        signal_type.append("刺透形态")

    if not signal_type:
        return None

    # === 2.5 过滤条件 ===
    # 近5日无跌停
    for i in range(max(0, n - 5), n):
        pct = safe_num(sub['pct_chg']).iloc[i]
        if pd.notna(pct) and float(pct) <= -9.5:
            return None

    # 市值 > 50亿
    mv = safe_num(sub.get('total_mv_billion'))
    if mv is not None and pd.notna(mv.iloc[-1]):
        if float(mv.iloc[-1]) < 50:
            return None

    # 量比(缩量程度, 用于排序)
    vol_ratio = vol_today / vol_avg5 if vol_avg5 > 0 else 1.0

    return {
        "signal_type": "+".join(signal_type),
        "vol_ratio": round(vol_ratio, 4),
        "dist_ma10_pct": round(dist_ma10 * 100, 2),
        "dist_ma20_pct": round(dist_ma20 * 100, 2),
        "near_support": "MA10" if near_ma10 else "MA20",
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    cal = load_trade_calendar(START_DATE, END_DATE, DATA)
    cal_set = set(cal)
    meta = load_universe(DATA)

    print(f"[INFO] preparing universe: {len(meta)}")
    meta, code_data, code_idx, rotation_map = build_prepared_universe(
        START_DATE, END_DATE, DATA, min_rows=40,
    )
    print(f"[INFO] usable codes: {len(code_data)}")

    cash = INITIAL_CAPITAL
    positions: List[Position] = []
    trades = []
    nav_rows = []

    # 统计计数
    tp1_count = 0
    tp2_count = 0
    trailing_sl_count = 0
    ma20_sl_count = 0
    time_sl_count = 0
    hard_sl_count = 0

    total_days = len(cal)
    for day_i, td in enumerate(cal):
        if day_i % 50 == 0:
            print(f"[INFO] processing {td} ({day_i}/{total_days})")

        # =============================================
        # 1) 先处理平仓
        # =============================================
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
            low = float(row["low"])

            pnl_pct = (close - p.buy_price) / p.buy_price

            # TP2: +15% 全走
            if not p.tp1_done and high >= p.buy_price * (1 + TP2_PCT):
                sell_price = p.buy_price * (1 + TP2_PCT)
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append(_make_trade(p, td, sell_price, "tp2_full", fee))
                tp2_count += 1
                continue

            # TP1: +8% 卖半仓
            if not p.tp1_done and high >= p.buy_price * (1 + TP1_PCT):
                sell_shares = p.shares // 2
                if sell_shares < LOT_SIZE:
                    sell_shares = p.shares
                sell_price = p.buy_price * (1 + TP1_PCT)
                fee = _sell_fee(sell_price, sell_shares)
                proceeds = sell_price * sell_shares - fee
                cash += proceeds
                trades.append(_make_trade(p, td, sell_price, "tp1_partial", fee, sell_shares))
                tp1_count += 1
                p.shares -= sell_shares
                p.tp1_done = True
                p.trailing_stop_price = low * (1 - TRAILING_SL_PCT)
                if p.shares <= 0:
                    continue

            # TP1后回撤止损
            if p.tp1_done and p.trailing_stop_price > 0 and close <= p.trailing_stop_price:
                sell_price = close
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append(_make_trade(p, td, sell_price, "trailing_sl", fee))
                trailing_sl_count += 1
                continue

            # 硬止损 -5%
            if pnl_pct <= HARD_STOP_PCT:
                sell_price = close
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append(_make_trade(p, td, sell_price, "hard_stop", fee))
                hard_sl_count += 1
                continue

            # MA20破位止损: 计算当日MA20, 收盘跌破则卖
            if idx >= 20:
                ma20_val = float(safe_num(df["close"]).iloc[idx - 19:idx + 1].mean())
                if close < ma20_val:
                    sell_price = close
                    fee = _sell_fee(sell_price, p.shares)
                    proceeds = sell_price * p.shares - fee
                    cash += proceeds
                    trades.append(_make_trade(p, td, sell_price, "ma20_sl", fee))
                    ma20_sl_count += 1
                    continue

            # 时间止损: 8天到期
            if held >= MAX_HOLD_DAYS:
                sell_price = close
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append(_make_trade(p, td, sell_price, "time_stop", fee))
                time_sl_count += 1
                continue

            remain_positions.append(p)

        positions = remain_positions

        # =============================================
        # 2) 扫描当日信号
        # =============================================
        free_slots = max(0, MAX_POSITIONS - len(positions))
        can_open = min(MAX_NEW_PER_DAY, free_slots)

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

                # 检查次日是否交易日
                next_row = df.iloc[idx + 1]
                if str(next_row["trade_date"]) not in cal_set:
                    continue

                # 已持有不重复买
                if any(p.code == code for p in positions):
                    continue

                sig = check_pullback_signal(df, idx)
                if sig is None:
                    continue

                sigs.append({
                    "code": code,
                    "name": r.name,
                    "industry": r.industry,
                    "signal_date": td,
                    "next_date": str(next_row["trade_date"]),
                    "signal_close": float(df.iloc[idx]["close"]),
                    "next_open": float(next_row["open"]),
                    "next_low": float(next_row["low"]),
                    "vol_ratio": sig["vol_ratio"],
                    "signal_type": sig["signal_type"],
                    "near_support": sig["near_support"],
                })

        # =============================================
        # 3) 排序 + 开仓 (按缩量程度排序)
        # =============================================
        if can_open > 0 and sigs:
            sigs.sort(key=lambda s: s["vol_ratio"])
            opened = 0
            for s in sigs:
                if opened >= can_open:
                    break

                buy_price = min(s["signal_close"] * 0.993, s["next_open"] * 0.988)

                # 低吸成交判断
                if s["next_low"] > buy_price:
                    continue

                budget = cash * POSITION_PCT
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
                    buy_date=s["next_date"], buy_price=buy_price,
                    shares=shares, initial_shares=shares,
                ))
                opened += 1

        # =============================================
        # 4) 记录净值
        # =============================================
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

    # =============================================
    # 统计输出
    # =============================================
    nav = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()

    final_equity = float(nav.iloc[-1]["total_equity"]) if not nav.empty else INITIAL_CAPITAL
    total_return = (final_equity / INITIAL_CAPITAL - 1) * 100

    eq = nav["total_equity"].values
    peak = np.maximum.accumulate(eq)
    drawdown = (eq - peak) / peak * 100
    max_dd = float(drawdown.min())

    years = (pd.Timestamp(END_DATE) - pd.Timestamp(START_DATE)).days / 365.25
    cagr = ((final_equity / INITIAL_CAPITAL) ** (1 / years) - 1) * 100 if years > 0 else 0

    win_rate = float((trades_df["net_pnl"] > 0).mean() * 100) if not trades_df.empty else 0.0
    trade_count = len(trades_df)

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

    # 退出原因统计
    exit_stats = {}
    if not trades_df.empty:
        for reason, grp in trades_df.groupby("exit_reason"):
            exit_stats[reason] = {
                "count": int(len(grp)),
                "avg_pnl": round(float(grp["net_pnl"].mean()), 2),
                "total_pnl": round(float(grp["net_pnl"].sum()), 2),
                "win_rate": round(float((grp["net_pnl"] > 0).mean() * 100), 2),
            }

    # 止跌信号统计
    signal_stats = {}
    if not trades_df.empty and "signal_type" in trades_df.columns:
        for sig, grp in trades_df.groupby("signal_type"):
            signal_stats[sig] = {
                "count": int(len(grp)),
                "win_rate": round(float((grp["net_pnl"] > 0).mean() * 100), 2),
                "avg_pnl": round(float(grp["net_pnl"].mean()), 2),
            }

    summary = {
        "version": VERSION_TAG,
        "strategy": "缩量回调低吸V1",
        "start_date": START_DATE,
        "end_date": END_DATE,
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "trade_count": trade_count,
        "win_rate_pct": round(win_rate, 2),
        "cagr_pct": round(cagr, 2),
        "exit_stats": exit_stats,
        "signal_stats": signal_stats,
        "tp_sl_counts": {
            "tp1_partial": tp1_count,
            "tp2_full": tp2_count,
            "trailing_sl": trailing_sl_count,
            "ma20_sl": ma20_sl_count,
            "time_stop": time_sl_count,
            "hard_stop": hard_sl_count,
        },
        "yearly_breakdown": yearly,
        "baseline_ref": "+219.99% / 585笔 / 50.6%WR / -16.16%DD / CAGR 42.99%",
    }

    nav.to_csv(OUT / f"sim_replay_20230101_{VERSION_TAG}_nav.csv", index=False, encoding="utf-8-sig")
    trades_df.to_csv(OUT / f"sim_replay_20230101_{VERSION_TAG}_trades.csv", index=False, encoding="utf-8-sig")
    (OUT / f"sim_replay_20230101_{VERSION_TAG}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _make_trade(p: Position, sell_date: str, sell_price: float, exit_reason: str,
                fee: float, sell_shares: int = None) -> dict:
    shares = sell_shares if sell_shares is not None else p.shares
    proceeds = sell_price * shares - fee
    return {
        "code": p.code, "name": p.name, "industry": p.industry,
        "buy_date": p.buy_date, "sell_date": sell_date,
        "buy_price": round(p.buy_price, 4),
        "sell_price": round(sell_price, 4),
        "shares": shares,
        "gross_pnl": round((sell_price - p.buy_price) * shares, 4),
        "fees": round(_buy_fee(p.buy_price, p.initial_shares) + fee, 4),
        "net_pnl": round(proceeds - p.buy_price * shares - _buy_fee(p.buy_price, p.initial_shares), 4),
        "exit_reason": exit_reason,
    }


if __name__ == "__main__":
    main()
