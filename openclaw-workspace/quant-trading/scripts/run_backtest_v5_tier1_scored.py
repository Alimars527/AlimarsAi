#!/usr/bin/env python3
"""
V5-T1 回测 + 仓位评分版（TaskD）

基于原始 run_simulated_paper_backtest_20230101_brick_v5_tier1.py
核心变更：用 position_scorer 替代等权开仓

变更点：
  - 每个信号先评分，≤5分不开仓
  - 仓位按评分映射：6→10%, 7→20%, 8→30%, 9→40%, 10→50%
  - OMAV>2%时仓位×1.3
  - trades CSV 新增 score/position_pct 列
  - 输出对比摘要

输出：
  outputs/sim_replay_20230101_brick_v5_tier1_scored_summary.json
  outputs/sim_replay_20230101_brick_v5_tier1_scored_trades.csv
  outputs/sim_replay_20230101_brick_v5_tier1_scored_nav.csv
"""

from __future__ import annotations
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
OUT = ROOT / "outputs"

START_DATE = "20230101"
END_DATE = "20260403"
INITIAL_CAPITAL = 100000.0
LOT_SIZE = 100
COMMISSION_RATE = 0.000086
MIN_COMMISSION = 5.0
STAMP_TAX_SELL = 0.0005


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
    score: int = 0
    position_pct: float = 0.0


def _commission(amount: float) -> float:
    return max(amount * COMMISSION_RATE, MIN_COMMISSION)


def _buy_fee(price: float, shares: int) -> float:
    return _commission(price * shares)


def _sell_fee(price: float, shares: int) -> float:
    amount = price * shares
    return _commission(amount) + amount * STAMP_TAX_SELL


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


# ─── 仓位评分（内联版，避免import循环） ───
# 板块关键词
T0_KW = ["半导体", "芯片", "AI", "算力", "AIDC", "IT设备", "软件",
         "互联网", "通信设备", "元器件", "计算机", "电子"]
T1_KW = ["光伏", "储能", "新能源", "锂电", "充电", "电池", "特斯拉"]
T2_KW = ["有色", "通信", "电力", "小金属", "铜", "铝", "矿"]
AVOID_KW = ["特高压", "商业航空", "房地产"]

SECTOR_MAP = {}
for kw in T0_KW: SECTOR_MAP[kw] = ("T0", 2.0)
for kw in T1_KW: SECTOR_MAP[kw] = ("T1", 1.5)
for kw in T2_KW: SECTOR_MAP[kw] = ("T2", 1.0)


def _score_sector(industry: str) -> float:
    for kw in AVOID_KW:
        if kw in industry:
            return 0.0
    for kw in T0_KW:
        if kw in industry:
            return 2.0
    for kw in T1_KW:
        if kw in industry:
            return 1.5
    for kw in T2_KW:
        if kw in industry:
            return 1.0
    return 0.5


def _score_rr_brick(close: float, white: float, yellow: float,
                    support: float = 0.0) -> float:
    """RR评分——砖型图版，信号自带1分基础分"""
    if pd.isna(close) or close <= 0:
        return 0.0
    stop = max(support, yellow * 0.98 if not pd.isna(yellow) and yellow > 0 else 0)
    risk = max(close - stop, close * 0.03)
    reward = close * 0.08
    rr = reward / risk if risk > 0 else 0
    if rr >= 2.5: return 3.0
    if rr >= 2.0: return 2.5
    if rr >= 1.5: return 2.0
    return 1.0  # 砖型图信号基础分


def _score_trend(white: float, yellow: float, close: float) -> float:
    if pd.isna(white) or pd.isna(yellow) or pd.isna(close):
        return 0.0
    s = 0.0
    if white > yellow: s += 0.5
    if close >= white * 0.995: s += 0.5
    spread = abs(white - yellow) / yellow * 100 if yellow > 0 else 0
    if white > yellow and spread >= 2.0: s += 0.5
    return s


def _score_volume(df, idx: int) -> float:
    if idx < 20 or 'vol' not in df.columns:
        return 0.5
    vol = safe_num(df['vol'])
    close = safe_num(df['close'])
    open_ = safe_num(df['open'])
    today_v = vol.iloc[idx]
    avg20 = vol.iloc[idx-20:idx].mean()
    if pd.isna(today_v) or pd.isna(avg20) or avg20 <= 0:
        return 0.5
    ratio = today_v / avg20
    s = 0.0
    if ratio >= 2.0: s += 1.0
    elif ratio >= 1.5: s += 0.7
    elif ratio >= 1.2: s += 0.4
    if close.iloc[idx] > open_.iloc[idx] and ratio >= 1.3:
        s += 0.5
    return min(s, 2.0)


def _score_signal(green_streak: int) -> float:
    s = 0.5  # 砖型图信号基础分
    if green_streak >= 4: s += 0.3
    if green_streak >= 5: s += 0.2
    return min(s, 1.0)


def score_signal_fast(df, idx: int, industry: str) -> tuple:
    """快速评分——返回 (总分int, position_pct float)"""
    row = df.iloc[idx]
    close = float(safe_num(row.get("close", 0)))
    white = float(safe_num(row.get("white_line", np.nan)))
    yellow = float(safe_num(row.get("yellow_line", np.nan)))

    # 支撑位
    low10 = safe_num(df['low'].iloc[max(0,idx-10):idx])
    support = float(low10.min()) if len(low10) > 0 else 0.0

    # 绿砖连续天数（简化：从idx往前数brick_formula_green=True的连续天数）
    green = df.get("brick_formula_green", pd.Series(dtype=bool))
    streak = 0
    for j in range(idx, max(idx-10, -1), -1):
        if j >= 0 and j < len(green) and bool(green.iloc[j]):
            streak += 1
        else:
            break

    rr = _score_rr_brick(close, white, yellow, support)
    sector = _score_sector(industry)
    trend = _score_trend(white, yellow, close)
    volume = _score_volume(df, idx)
    signal = _score_signal(streak)

    raw = rr + sector + trend + volume + signal
    total = max(0, min(10, int(round(raw))))

    # 仓位映射
    pos_map = {0:0, 1:0, 2:0, 3:0, 4:0, 5:0, 6:10, 7:20, 8:30, 9:40, 10:50}
    return total, float(pos_map.get(total, 0))


# ─── 回测主逻辑（与原版结构一致） ───

EXCLUDED_INDUSTRIES = {
    '航空', '电气设备', '旅游服务', '黄金', '全国地产',
    '轻工机械', '农药化肥', '石油贸易', '矿物制品', '专用机械',
    '化纤', '装修装饰', '其他商业', '焦炭加工',
}


def load_omav() -> pd.DataFrame:
    p = DATA / "omav" / "omav_daily_standardized_20260402.csv"
    df = pd.read_csv(p, dtype={"trade_date": str})
    df = df.sort_values("trade_date").reset_index(drop=True)
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

    print(f"[SCORED-BT] preparing universe: {len(meta)}")
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

    print(f"[SCORED-BT] usable codes: {len(code_data)}")

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

    trading_meta = meta[~meta["industry"].isin(EXCLUDED_INDUSTRIES)].copy()
    print(f"[SCORED-BT] rotation_map from {len(meta)} stocks, trading: {len(trading_meta)}")

    cash = INITIAL_CAPITAL
    positions: List[Position] = []
    trades = []
    nav_rows = []

    # 统计
    score_skip_count = 0  # 因评分≤5被跳过的信号数
    score_distribution = {}  # {score: count}

    for td in cal:
        # 1) 平仓
        remain = []
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
                "code": p.code, "name": p.name, "industry": p.industry,
                "strategy": p.strategy, "buy_date": p.buy_date, "sell_date": td,
                "buy_price": round(p.buy_price, 4), "sell_price": round(sell_price, 4),
                "shares": p.shares, "score": p.score, "position_pct": p.position_pct,
                "gross_pnl": round((sell_price - p.buy_price) * p.shares, 4),
                "fees": round(_buy_fee(p.buy_price, p.shares) + fee, 4),
                "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.shares), 4),
            })
        positions = remain

        # 2) 环境控制
        om = omav_map.get(td, {})
        bear = str(om.get("omav_bear_regime_flag", "False")).lower() == "true"
        warn = str(om.get("omav_rotation_warning_flag", "False")).lower() == "true"
        omav_val = float(safe_num(om.get("omav_value", 0))) if not pd.isna(om.get("omav_value")) else 0.0

        max_new = 0 if bear else (1 if warn else 3)
        max_total_pos = 1 if warn else 3
        free_slots = max(0, max_total_pos - len(positions))
        can_open = min(max_new, free_slots)
        warn_overlap_only = bool(warn and not bear)

        sigs = []
        if can_open > 0:
            for r in trading_meta.itertuples(index=False):
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

                # BRICK_V5_T1 信号
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
                        and pd.notna(white) and pd.notna(yellow) and pd.notna(high)
                        and high >= white and white > yellow
                        and g.iloc[idx-1] and g.iloc[idx-2] and g.iloc[idx-3] and g.iloc[idx-4]
                        and z.iloc[idx-4] > z.iloc[idx-3] > z.iloc[idx-2] > z.iloc[idx-1]
                        and z.iloc[idx] >= z.iloc[idx-1]
                    )

                if warn_overlap_only and not brick:
                    continue
                if not brick:
                    continue

                # ★ 评分 ★
                score, pos_pct = score_signal_fast(df, idx, r.industry)

                # OMAV调整
                if omav_val > 2.0 and pos_pct > 0:
                    pos_pct = min(pos_pct * 1.3, 50.0)

                score_distribution[score] = score_distribution.get(score, 0) + 1

                # 方案B：不过滤信号，评分仅排序+仓位微调
                sigs.append({
                    "code": code, "name": r.name, "industry": r.industry,
                    "signal_date": td, "next_date": str(next_row["trade_date"]),
                    "signal_close": float(row["close"]),
                    "next_open": float(next_row["open"]),
                    "next_low": float(next_row["low"]),
                    "score": score,
                    "brick": brick,
                    "j": float(safe_num(row.get("kdj_j"))) if pd.notna(safe_num(row.get("kdj_j"))) else 999,
                })

        # 3) 按评分排序开仓
        if can_open > 0 and sigs:
            sigs.sort(key=lambda s: (-s["score"], s["j"]))
            selected = sigs[:can_open * 2]

            opened = 0
            for s in selected:
                if opened >= can_open:
                    break

                buy_price = min(s["signal_close"] * 0.995, s["next_open"] * 0.99)
                hold_days = 1

                if s["next_low"] > buy_price:
                    continue

                # ★ 方案B：等权基础 + 评分微调仓位 ★
                # 等权基础仓位：cash / slots
                base_budget = cash / can_open
                # 评分微调：8-10分+20%, 6-7分正常, ≤5分-20%
                if s["score"] >= 8:
                    budget = base_budget * 1.2
                elif s["score"] >= 6:
                    budget = base_budget
                else:
                    budget = base_budget * 0.8
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
                    strategy="BRICK_V5_T1_SCOREB", buy_date=s["next_date"],
                    buy_price=buy_price, shares=shares, hold_days=hold_days,
                    initial_shares=shares, score=s["score"], position_pct=round(budget/cash*100, 1),
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
            "trade_date": td, "cash": round(cash, 2),
            "market_value": round(mv, 2), "total_equity": round(cash + mv, 2),
            "positions": len(positions),
        })

    # ─── 汇总 ───
    nav = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)

    final_equity = float(nav.iloc[-1]["total_equity"]) if not nav.empty else INITIAL_CAPITAL
    total_return = (final_equity / INITIAL_CAPITAL - 1) * 100

    # 最大回撤
    eq = nav["total_equity"].values
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak * 100
    max_dd = float(dd.min())

    # 胜率
    wr = float((trades_df["net_pnl"] > 0).mean() * 100) if not trades_df.empty else 0.0

    # 盈亏比
    wins = trades_df[trades_df["net_pnl"] > 0]["net_pnl"]
    losses = trades_df[trades_df["net_pnl"] <= 0]["net_pnl"]
    avg_win = float(wins.mean()) if len(wins) > 0 else 0
    avg_loss = abs(float(losses.mean())) if len(losses) > 0 else 1
    pf = avg_win / avg_loss if avg_loss > 0 else 0

    # 年化
    n_days = len(nav)
    years = n_days / 250
    cagr = ((final_equity / INITIAL_CAPITAL) ** (1/years) - 1) * 100 if years > 0 else 0

    # 按评分分组的胜率
    score_wr = {}
    if not trades_df.empty:
        for sc in sorted(trades_df["score"].unique()):
            sub = trades_df[trades_df["score"] == sc]
            score_wr[int(sc)] = {
                "count": len(sub),
                "win_rate": round(float((sub["net_pnl"] > 0).mean() * 100), 1),
                "avg_pnl": round(float(sub["net_pnl"].mean()), 2),
                "total_pnl": round(float(sub["net_pnl"].sum()), 2),
            }

    summary = {
        "version": "V5_T1_SCOREB",
        "description": "评分仅排序+微调仓位(不过滤), 8-10分+20%, 6-7分等权, ≤5分-20%",
        "start_date": START_DATE,
        "end_date": END_DATE,
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "trade_count": len(trades_df),
        "win_rate_pct": round(wr, 2),
        "profit_factor": round(pf, 2),
        "cagr_pct": round(cagr, 2),
        "score_skip_count": score_skip_count,
        "score_distribution": {str(k): v for k, v in sorted(score_distribution.items())},
        "score_win_rates": score_wr,
        "baseline_v5_t1": "+181.50% / 552笔 / 胜率52.17% / 回撤13.65%",
    }

    nav.to_csv(OUT / "sim_replay_20230101_brick_v5_tier1_scoreb_nav.csv", index=False, encoding="utf-8-sig")
    trades_df.to_csv(OUT / "sim_replay_20230101_brick_v5_tier1_scoreb_trades.csv", index=False, encoding="utf-8-sig")
    (OUT / "sim_replay_20230101_brick_v5_tier1_scoreb_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
