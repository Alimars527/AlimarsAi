#!/usr/bin/env python3
"""
10w 模拟实盘节奏回放（实验版：B1实验版 v1 + 严格版砖型图V3）
- 策略：B1_V2 + BRICK_V3（与你当前模拟实盘主线一致）
- 环境：OMAV 极致空头不新开仓；转弱降频；B1实验版：新B1公式 + 10日弱势退出 + 黄线止损 + 10%/20%分批止盈 + 高位转弱退出
- 执行：
  * B1:  买入价=min(C*0.993, next_open*0.988)，持有3天后卖出
  * Brick: 买入价=min(C*0.995, next_open*0.99)，持有1天后卖出
- 资金：10w 起步，A股100股一手

输出：
- outputs/sim_replay_20230101_b1_experimental_v1_strict_brick_v3_summary.json
- outputs/sim_replay_20230101_b1_experimental_v1_strict_brick_v3_trades.csv
- outputs/sim_replay_20230101_b1_experimental_v1_strict_brick_v3_nav.csv
"""

from __future__ import annotations
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
OUT = ROOT / "outputs"

START_DATE = "20230101"
END_DATE = pd.read_csv(DATA / "daily" / "000001.SZ.csv", dtype={"trade_date": str})["trade_date"].drop_duplicates().sort_values().iloc[-1]
INITIAL_CAPITAL = 100000.0
LOT_SIZE = 100
COMMISSION_RATE = 0.000086
MIN_COMMISSION = 5.0
STAMP_TAX_SELL = 0.0005
RR_RATIO_MIN = 1.5
B1_MAX_HOLD_DAYS = 10
B1_WEAK_EXIT_PCT = 0.05
B1_TP1 = 0.10
B1_TP2 = 0.20


@dataclass
class Position:
    code: str
    name: str
    industry: str
    strategy: str  # B1_EXPERIMENTAL / BRICK_V3
    buy_date: str
    buy_price: float
    shares: int
    hold_days: int
    initial_shares: int = 0
    tp1_done: bool = False
    tp2_done: bool = False


def _commission(amount: float) -> float:
    return max(amount * COMMISSION_RATE, MIN_COMMISSION)


def _buy_fee(price: float, shares: int) -> float:
    return _commission(price * shares)


def _sell_fee(price: float, shares: int) -> float:
    amount = price * shares
    return _commission(amount) + amount * STAMP_TAX_SELL


def j_threshold(td: str) -> float:
    y = td[:4]
    if y == "2023":
        return -10
    if y == "2024":
        return 0
    if y == "2025":
        return 18
    return 25


def safe_num(v):
    return pd.to_numeric(v, errors="coerce")


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


def load_omav() -> pd.DataFrame:
    p = DATA / "omav" / "omav_daily_standardized_20260402.csv"
    df = pd.read_csv(p, dtype={"trade_date": str})
    df = df.sort_values("trade_date").reset_index(drop=True)
    # 兜底：如果列不存在，就按规则临时计算
    if "omav_rotation_warning_flag" not in df.columns:
        df["omav_rotation_warning_flag"] = safe_num(df.get("omav_value")).fillna(0) <= -2.3
    if "omav_bear_regime_flag" not in df.columns:
        if "omav_5day_sum" in df.columns:
            df["omav_bear_regime_flag"] = safe_num(df["omav_5day_sum"]).fillna(0) < -5
        else:
            v = safe_num(df.get("omav_value")).fillna(0)
            df["omav_bear_regime_flag"] = v.rolling(5).sum() < -5
    return df


def load_trade_calendar() -> List[str]:
    cal = pd.read_csv(DATA / "daily" / "000001.SZ.csv", dtype={"trade_date": str})[["trade_date"]]
    cal = cal.drop_duplicates().sort_values("trade_date")
    return [d for d in cal["trade_date"].tolist() if START_DATE <= d <= END_DATE]


def load_universe() -> pd.DataFrame:
    meta = pd.read_csv(DATA / "meta" / "stock_basic.csv", dtype=str).fillna("")
    meta = meta[~meta["ts_code"].str.endswith(".BJ")]
    meta = meta[~meta["name"].str.upper().str.contains("ST", na=False)]
    meta = meta[~meta["industry"].str.contains("房地产", na=False)]
    meta = meta[meta["industry"] != "银行"]
    # 当前口径：不做创业板
    meta = meta[~meta["ts_code"].str.startswith("300")]
    return meta[["ts_code", "name", "industry", "list_date"]].copy()


def prepare_code_df(code: str) -> Optional[pd.DataFrame]:
    from quant.indicators import add_tactic_base_indicators
    from quant.brick_formula import add_brick_formula_flags

    p_daily = DATA / "daily" / f"{code}.csv"
    p_basic = DATA / "daily_basic" / f"{code}.csv"
    if not p_daily.exists() or not p_basic.exists():
        return None

    try:
        d = pd.read_csv(p_daily, dtype={"trade_date": str}).sort_values("trade_date").reset_index(drop=True)
        b = pd.read_csv(p_basic, dtype={"trade_date": str})
        if d.empty or "trade_date" not in d.columns:
            return None

        for c in ["open", "high", "low", "close", "vol", "pct_chg"]:
            if c in d.columns:
                d[c] = safe_num(d[c])

        if "total_mv" in b.columns:
            b = b[["trade_date", "total_mv"]].copy()
            b["total_mv_billion"] = safe_num(b["total_mv"]) / 10000.0
            d = d.merge(b[["trade_date", "total_mv_billion"]], on="trade_date", how="left")
        else:
            d["total_mv_billion"] = pd.NA

        d = add_tactic_base_indicators(d)
        d = add_brick_formula_flags(d)

        # 需要列兜底
        for c in ["brick_formula_green", "brick_raw_turn_red", "brick_history_ok"]:
            if c not in d.columns:
                d[c] = False
        if "brick_formula_value" not in d.columns:
            d["brick_formula_value"] = 0.0

        d = d[(d["trade_date"] >= START_DATE) & (d["trade_date"] <= END_DATE)].copy()
        if d.empty:
            return None
        return d.reset_index(drop=True)
    except Exception:
        return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    omav = load_omav()
    omav_map = omav.set_index("trade_date").to_dict("index")
    cal = load_trade_calendar()
    cal_set = set(cal)

    meta = load_universe()

    code_data: Dict[str, pd.DataFrame] = {}
    code_idx: Dict[str, Dict[str, int]] = {}
    industry_daily_ret_rows = []

    print(f"[INFO] preparing universe: {len(meta)}")
    for r in meta.itertuples(index=False):
        c = r.ts_code
        df = prepare_code_df(c)
        if df is None or len(df) < 40:
            continue
        code_data[c] = df
        code_idx[c] = {td: i for i, td in enumerate(df["trade_date"].tolist())}
        t = df[["trade_date", "pct_chg"]].copy()
        t["industry"] = r.industry
        industry_daily_ret_rows.append(t)

    print(f"[INFO] usable codes: {len(code_data)}")

    if not industry_daily_ret_rows:
        raise RuntimeError("no usable codes")

    ind_df = pd.concat(industry_daily_ret_rows, ignore_index=True)
    ind_df["pct_chg"] = safe_num(ind_df["pct_chg"])
    board = (
        ind_df.groupby(["trade_date", "industry"], as_index=False)["pct_chg"]
        .mean()
        .sort_values(["trade_date", "pct_chg"], ascending=[True, False])
    )
    board["rank"] = board.groupby("trade_date")["pct_chg"].rank(method="first", ascending=False)
    board_top5 = board[board["rank"] <= 5].copy()
    rotation_map = board_top5.assign(flag=True).set_index(["trade_date", "industry"])["flag"].to_dict()

    cash = INITIAL_CAPITAL
    positions: List[Position] = []
    trades = []
    nav_rows = []

    for td in cal:
        # 1) 先处理平仓（按收盘）
        remain_positions = []
        for p in positions:
            idx_map = code_idx.get(p.code, {})
            if td not in idx_map:
                remain_positions.append(p)
                continue
            idx = idx_map[td]
            df = code_data[p.code]
            # 计算已持有交易日
            buy_idx = idx_map.get(p.buy_date)
            if buy_idx is None:
                remain_positions.append(p)
                continue
            held = idx - buy_idx
            if held < p.hold_days:
                remain_positions.append(p)
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
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.shares), 4),
                }
            )

        positions = remain_positions

        # 2) 生成当日信号，并尝试在“下一交易日”按规则成交
        # 环境控制
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
                # BRICK_V3
                brick_v1 = bool(row.get("brick_raw_turn_red", False)) and bool(row.get("brick_history_ok", False))
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

                if warn_overlap_only and not (b1 and brick):
                    continue

                if not (b1 or brick):
                    continue

                sigs.append(
                    {
                        "code": code,
                        "name": r.name,
                        "industry": r.industry,
                        "signal_date": td,
                        "next_date": str(next_row["trade_date"]),
                        "signal_close": float(row["close"]),
                        "next_open": float(next_row["open"]),
                        "next_low": float(next_row["low"]),
                        "b1": b1,
                        "brick": brick,
                        "j": float(safe_num(row.get("kdj_j"))) if pd.notna(safe_num(row.get("kdj_j"))) else 999,
                    }
                )

        # 3) 排序 + 开仓
        if can_open > 0 and sigs:
            def _rank(s):
                # 重合 > brick > b1
                p = 0 if (s["b1"] and s["brick"]) else (1 if s["brick"] else 2)
                return (p, s["j"])

            sigs = sorted(sigs, key=_rank)
            selected = sigs[: can_open * 2]  # 多看一点，避免不成交

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

                # 低吸成交判断
                if s["next_low"] > buy_price:
                    continue

                # 单笔等权
                slots_left = max(1, can_open - opened)
                budget = cash / slots_left
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

        # 4) 记录当日净值（按收盘估值）
        mv = 0.0
        for p in positions:
            idx_map = code_idx.get(p.code, {})
            if td in idx_map:
                px = float(code_data[p.code].iloc[idx_map[td]]["close"])
                mv += px * p.shares
            else:
                mv += p.buy_price * p.shares

        nav_rows.append(
            {
                "trade_date": td,
                "cash": round(cash, 2),
                "market_value": round(mv, 2),
                "total_equity": round(cash + mv, 2),
                "positions": len(positions),
            }
        )

    nav = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)

    final_equity = float(nav.iloc[-1]["total_equity"]) if not nav.empty else INITIAL_CAPITAL
    total_return = (final_equity / INITIAL_CAPITAL - 1) * 100

    summary = {
        "start_date": START_DATE,
        "end_date": END_DATE,
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return, 2),
        "trade_count": int(len(trades_df)),
        "win_rate_pct": round(float((trades_df["net_pnl"] > 0).mean() * 100), 2) if not trades_df.empty else 0.0,
        "nav_path": str(OUT / "sim_replay_20230101_b1_experimental_v1_strict_brick_v3_nav.csv"),
        "trades_path": str(OUT / "sim_replay_20230101_b1_experimental_v1_strict_brick_v3_trades.csv"),
    }

    nav.to_csv(OUT / "sim_replay_20230101_b1_experimental_v1_strict_brick_v3_nav.csv", index=False, encoding="utf-8-sig")
    trades_df.to_csv(OUT / "sim_replay_20230101_b1_experimental_v1_strict_brick_v3_trades.csv", index=False, encoding="utf-8-sig")
    (OUT / "sim_replay_20230101_b1_experimental_v1_strict_brick_v3_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    latest_td = END_DATE
    pos_rows = []
    last_prices = {}
    for p in positions:
        idx_map = code_idx.get(p.code, {})
        if latest_td in idx_map:
            last_px = float(code_data[p.code].iloc[idx_map[latest_td]]["close"])
        else:
            last_px = float(p.buy_price)
        last_prices[p.code] = last_px
        pos_rows.append({
            "code": p.code,
            "name": p.name,
            "shares": int(p.shares),
            "cost": round(float(p.buy_price), 4),
            "last_price": round(last_px, 4),
            "market_value": round(last_px * p.shares, 2),
            "unrealized_pnl": round((last_px - p.buy_price) * p.shares, 2),
            "unrealized_pnl_pct": round((last_px / p.buy_price - 1) * 100, 2) if p.buy_price else 0.0,
            "strategy": p.strategy,
            "buy_date": p.buy_date,
        })
    pd.DataFrame(pos_rows).to_csv(OUT / "sim_positions.csv", index=False, encoding="utf-8-sig")
    sim_account = {
        "started_at": pd.Timestamp.now(tz='Asia/Shanghai').isoformat(),
        "updated_at": pd.Timestamp.now(tz='Asia/Shanghai').isoformat(),
        "mode": "paper_trading",
        "strategy_mode": "b1_experimental_v1_and_strict_brick_v3",
        "base_capital": INITIAL_CAPITAL,
        "cash": round(float(cash), 2),
        "market_value": round(float(nav.iloc[-1]["market_value"]) if not nav.empty else 0.0, 2),
        "total_equity": round(final_equity, 2),
        "positions": pos_rows,
        "notes": f"模拟实盘已启动；主线=B1实验版V1+严格砖型图V3；最新交易日={latest_td}。"
    }
    (OUT / "sim_account.json").write_text(json.dumps(sim_account, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("模拟实盘账户已写入:", OUT / "sim_account.json")


if __name__ == "__main__":
    main()
