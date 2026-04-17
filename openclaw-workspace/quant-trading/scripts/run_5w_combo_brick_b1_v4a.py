     1|#!/usr/bin/env python3
     2|"""
     3|10w 模拟实盘节奏回放（实验版：V4-A + avg5(1,2]50% + 纯B1窄修正 v1）
     4|- 策略：B1_V2 + BRICK_V3（与你当前模拟实盘主线一致）
     5|- 环境：OMAV 极致空头不新开仓；转弱降频；B1实验版：新B1公式 + 10日弱势退出 + 黄线止损 + 10%/20%分批止盈 + 高位转弱退出
     6|- 执行：
     7|  * B1:  买入价=min(C*0.993, next_open*0.988)，持有3天后卖出
     8|  * Brick: 买入价=min(C*0.995, next_open*0.99)，持有1天后卖出
     9|- 资金：10w 起步，A股100股一手
    10|
    11|输出：
    12|- outputs/sim_replay_20230101_b1_experimental_v1_strict_brick_v3_v4a_plus_avg5_band_1_2_deweight_05_narrowfix_v1_summary.json
    13|- outputs/sim_replay_20230101_b1_experimental_v1_strict_brick_v3_v4a_plus_avg5_band_1_2_deweight_05_narrowfix_v1_trades.csv
    14|- outputs/sim_replay_20230101_b1_experimental_v1_strict_brick_v3_v4a_plus_avg5_band_1_2_deweight_05_narrowfix_v1_nav.csv
    15|"""
    16|
    17|from __future__ import annotations
    18|import json
    19|import sys
    20|from dataclasses import dataclass
    21|from pathlib import Path
    22|from typing import Dict, List, Optional
    23|
    24|import pandas as pd
    25|
    26|from quant.sim_replay_common import (
    27|    build_prepared_universe,
    28|    load_omav,
    29|    load_trade_calendar,
    30|    load_universe,
    31|    prepare_code_df,
    32|    safe_num,
    33|)
    34|
    35|ROOT = Path(__file__).resolve().parents[1]
    36|sys.path.insert(0, str(ROOT))
    37|DATA = ROOT / "data"
    38|OUT = ROOT / "outputs"
    39|
    40|START_DATE = "20230101"
    41|END_DATE = "20260403"
    42|INITIAL_CAPITAL = 50000.0
    43|LOT_SIZE = 100
    44|COMMISSION_RATE = 0.000086
    45|MIN_COMMISSION = 5.0
    46|STAMP_TAX_SELL = 0.0005
    47|RR_RATIO_MIN = 1.5
    48|B1_MAX_HOLD_DAYS = 10
    49|B1_WEAK_EXIT_PCT = 0.05
    50|B1_TP1 = 0.10
    51|B1_TP2 = 0.20
    52|PROGRESS_PATH = OUT / "sim_replay_20230101_b1_experimental_v1_strict_brick_v3_v4a_plus_avg5_band_1_2_deweight_05_narrowfix_v1_progress.json"
    53|
    54|
    55|@dataclass
    56|class Position:
    57|    code: str
    58|    name: str
    59|    industry: str
    60|    strategy: str  # B1_EXPERIMENTAL / BRICK_V3
    61|    buy_date: str
    62|    buy_price: float
    63|    shares: int
    64|    hold_days: int
    65|    initial_shares: int = 0
    66|    tp1_done: bool = False
    67|    tp2_done: bool = False
    68|
    69|
    70|def _commission(amount: float) -> float:
    71|    return max(amount * COMMISSION_RATE, MIN_COMMISSION)
    72|
    73|
    74|def _buy_fee(price: float, shares: int) -> float:
    75|    return _commission(price * shares)
    76|
    77|
    78|def _sell_fee(price: float, shares: int) -> float:
    79|    amount = price * shares
    80|    return _commission(amount) + amount * STAMP_TAX_SELL
    81|
    82|
    83|def j_threshold(td: str) -> float:
    84|    y = td[:4]
    85|    if y == "2023":
    86|        return -10
    87|    if y == "2024":
    88|        return 0
    89|    if y == "2025":
    90|        return 18
    91|    return 25
    92|
    93|
    94|def _sma_cn(series: pd.Series, n: int, m: int) -> pd.Series:
    95|    x = safe_num(series).fillna(0.0)
    96|    out = []
    97|    prev = None
    98|    for v in x.tolist():
    99|        if prev is None:
   100|            prev = v
   101|        else:
   102|            prev = (m * v + (n - m) * prev) / n
   103|        out.append(prev)
   104|    return pd.Series(out, index=series.index)
   105|
   106|
   107|def save_progress(status: str, processed: int = 0, total: int = 0, message: str = ""):
   108|    pct = round(processed / total * 100, 2) if total else 0.0
   109|    PROGRESS_PATH.write_text(json.dumps({
   110|        "task": "b1_experimental_v1_strict_brick_v3_avg5_deweight_v1",
   111|        "status": status,
   112|        "processed": processed,
   113|        "total": total,
   114|        "progress_pct": pct,
   115|        "updated_at": pd.Timestamp.now(tz='Asia/Shanghai').isoformat(),
   116|        "message": message,
   117|    }, ensure_ascii=False, indent=2), encoding='utf-8')
   118|
   119|
   120|def b1_experimental_ok(df: pd.DataFrame, idx: int) -> bool:
   121|    sub = df.iloc[: idx + 1].copy().reset_index(drop=True)
   122|    if len(sub) < 160:
   123|        return False
   124|    C = safe_num(sub['close'])
   125|    O = safe_num(sub['open'])
   126|    H = safe_num(sub['high'])
   127|    L = safe_num(sub['low'])
   128|    VOL = safe_num(sub['vol']).fillna(0.0)
   129|    REAL_YANG = (C > O) & ~(C < C.shift(1))
   130|    REAL_YIN = (C < O) & ~(C > C.shift(1))
   131|    ll9 = L.rolling(9).min(); hh9 = H.rolling(9).max()
   132|    RSV = (C - ll9) / (hh9 - ll9) * 100
   133|    K = _sma_cn(RSV, 3, 1)
   134|    D = _sma_cn(K, 3, 1)
   135|    J = 3 * K - 2 * D
   136|    J_OK = J <= 13
   137|    VOL_YANG1 = (VOL * REAL_YANG.astype(int)).rolling(57).sum()
   138|    VOL_YIN1 = (VOL * REAL_YIN.astype(int)).rolling(57).sum()
   139|    VOL_YANG2 = (VOL * REAL_YANG.astype(int)).rolling(14).sum()
   140|    VOL_YIN2 = (VOL * REAL_YIN.astype(int)).rolling(14).sum()
   141|    YANGYIN_OK1 = VOL_YANG1 > 1.25 * VOL_YIN1
   142|    YANGYIN_OK2 = VOL_YANG2 > 2.25 * VOL_YIN2
   143|    MV = safe_num(sub.get('total_mv_billion'))
   144|    MVOK = MV >= 50
   145|    O85 = O.rolling(21).min() + 0.95 * (O.rolling(21).max() - O.rolling(21).min())
   146|    TOP15O = O >= O85
   147|    FD15 = (C < C.shift(1)) & (C <= O) & (VOL >= 1.2 * VOL.shift(1))
   148|    CNT28 = ((TOP15O & FD15).astype(int)).rolling(21).sum()
   149|    GOOD28 = CNT28 <= 0
   150|    AVG40 = VOL.rolling(40).mean()
   151|    PLRY = (VOL > 1.95 * VOL.shift(1)) & (C > O) & (VOL > AVG40)
   152|    PLRY_CNT = (((PLRY.astype(int)).rolling(14).sum() >= 2) | ((PLRY.astype(int)).rolling(57).sum() >= 4))
   153|    prev_plry = PLRY.shift(1).eq(True)
   154|    PLRY_FIRST = PLRY & (~prev_plry)
   155|    PLRY_CONT = PLRY & prev_plry
   156|    prev_real_yin = REAL_YIN.shift(1).eq(True)
   157|    PRE_NOT_REALYIN = ~prev_real_yin
   158|    HALF_DOWN = PRE_NOT_REALYIN & (C < C.shift(1)) & (VOL <= 0.5 * VOL.shift(1))
   159|    CNT_FIRST = PLRY_FIRST.astype(int).rolling(57).sum()
   160|    CNT_CONT = PLRY_CONT.astype(int).rolling(57).sum()
   161|    CNT_HALF = HALF_DOWN.astype(int).rolling(57).sum()
   162|    THREE_SUM_OK = (CNT_FIRST + CNT_CONT + CNT_HALF) >= 4
   163|    MAXVOL28 = VOL.rolling(28).max()
   164|    MAX28_BAD = (VOL == MAXVOL28) & REAL_YIN
   165|    MAX28_OK = MAX28_BAD.astype(int).rolling(28).sum() == 0
   166|    A1 = ((PLRY_CNT & YANGYIN_OK1 & J_OK & MVOK & GOOD28 & THREE_SUM_OK & MAX28_OK) | (PLRY_CNT & YANGYIN_OK2 & J_OK & MVOK & GOOD28 & MAX28_OK))
   167|    HMSHORTWL = sub['white_line']
   168|    HMLONGYL = sub['yellow_line']
   169|    B1 = (HMSHORTWL >= HMLONGYL * 0.985) & (C >= HMLONGYL * 0.985) & A1
   170|    return bool(B1.iloc[-1])
   171|
   172|
   173|def main():
   174|    OUT.mkdir(parents=True, exist_ok=True)
   175|
   176|    omav = load_omav(DATA)
   177|    omav_map = omav.set_index("trade_date").to_dict("index")
   178|    omav_avg5_map = {}
   179|    if "trade_date" in omav.columns:
   180|        om2 = omav.copy().sort_values("trade_date").reset_index(drop=True)
   181|        val_col = "omav" if "omav" in om2.columns else ("omav_value" if "omav_value" in om2.columns else None)
   182|        if val_col is not None:
   183|            om2[val_col] = safe_num(om2[val_col])
   184|            om2["avg5_prev"] = om2[val_col].shift(1).rolling(5).mean()
   185|            omav_avg5_map = om2.set_index("trade_date")["avg5_prev"].to_dict()
   186|    cal = load_trade_calendar(START_DATE, END_DATE, DATA)
   187|    cal_set = set(cal)
   188|
   189|    meta = load_universe(DATA)
   190|
   191|    print(f"[INFO] preparing universe: {len(meta)}")
   192|    meta, code_data, code_idx, rotation_map = build_prepared_universe(
   193|        START_DATE,
   194|        END_DATE,
   195|        DATA,
   196|        min_rows=40,
   197|    )
   198|
   199|    print(f"[INFO] usable codes: {len(code_data)}")
   200|
   201|    if not rotation_map:
   202|        raise RuntimeError("no usable codes")
   203|
   204|    save_progress("running", 0, len(cal), "starting")
   205|    cash = INITIAL_CAPITAL
   206|    positions: List[Position] = []
   207|    trades = []
   208|    nav_rows = []
   209|
   210|    for td in cal:
   211|        # 1) 先处理平仓（按收盘）
   212|        remain_positions = []
   213|        for p in positions:
   214|            idx_map = code_idx.get(p.code, {})
   215|            if td not in idx_map:
   216|                remain_positions.append(p)
   217|                continue
   218|            idx = idx_map[td]
   219|            df = code_data[p.code]
   220|            # 计算已持有交易日
   221|            buy_idx = idx_map.get(p.buy_date)
   222|            if buy_idx is None:
   223|                remain_positions.append(p)
   224|                continue
   225|            held = idx - buy_idx
   226|            if held < p.hold_days:
   227|                remain_positions.append(p)
   228|                continue
   229|
   230|            sell_price = float(df.iloc[idx]["close"])
   231|            fee = _sell_fee(sell_price, p.shares)
   232|            proceeds = sell_price * p.shares - fee
   233|            cash += proceeds
   234|            trades.append(
   235|                {
   236|                    "code": p.code,
   237|                    "name": p.name,
   238|                    "industry": p.industry,
   239|                    "strategy": p.strategy,
   240|                    "buy_date": p.buy_date,
   241|                    "sell_date": td,
   242|                    "buy_price": round(p.buy_price, 4),
   243|                    "sell_price": round(sell_price, 4),
   244|                    "shares": p.shares,
   245|                    "gross_pnl": round((sell_price - p.buy_price) * p.shares, 4),
   246|                    "fees": round(_buy_fee(p.buy_price, p.shares) + fee, 4),
   247|                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.shares), 4),
   248|                }
   249|            )
   250|
   251|        positions = remain_positions
   252|
   253|        # 2) 生成当日信号，并尝试在“下一交易日”按规则成交
   254|        # 环境控制
   255|        om = omav_map.get(td, {})
   256|        bear = str(om.get("omav_bear_regime_flag", "False")).lower() == "true"
   257|        warn = str(om.get("omav_rotation_warning_flag", "False")).lower() == "true"
   258|
   259|        max_new = 0 if bear else (1 if warn else 3)
   260|        max_total_pos = 1 if warn else 3
   261|        free_slots = max(0, max_total_pos - len(positions))
   262|        can_open = min(max_new, free_slots)
   263|        warn_overlap_only = bool(warn and not bear)
   264|
   265|        sigs = []
   266|        if can_open > 0:
   267|            for r in meta.itertuples(index=False):
   268|                code = r.ts_code
   269|                if code not in code_data:
   270|                    continue
   271|                idx_map = code_idx[code]
   272|                if td not in idx_map:
   273|                    continue
   274|
   275|                idx = idx_map[td]
   276|                df = code_data[code]
   277|                if idx < 25 or idx + 1 >= len(df):
   278|                    continue
   279|
   280|                row = df.iloc[idx]
   281|                next_row = df.iloc[idx + 1]
   282|                if str(next_row["trade_date"]) not in cal_set:
   283|                    continue
   284|
   285|                b1 = b1_experimental_ok(df, idx)
   286|                # BRICK_V3
   287|                brick_v1 = bool(row.get("brick_raw_turn_red", False)) and bool(row.get("brick_history_ok", False))
   288|                brick = False
   289|                if brick_v1 and (not bear) and (not warn) and idx >= 4:
   290|                    z = safe_num(df["brick_formula_value"]).fillna(0)
   291|                    g = df["brick_formula_green"].fillna(False).astype(bool)
   292|                    white = safe_num(row.get("white_line"))
   293|                    yellow = safe_num(row.get("yellow_line"))
   294|                    high = safe_num(row.get("high"))
   295|                    rotation_ok = rotation_map.get((td, r.industry), False)
   296|                    brick = bool(
   297|                        rotation_ok
   298|                        and pd.notna(white)
   299|                        and pd.notna(yellow)
   300|                        and pd.notna(high)
   301|                        and high >= white
   302|                        and white > yellow
   303|                        and g.iloc[idx - 1]
   304|                        and g.iloc[idx - 2]
   305|                        and g.iloc[idx - 3]
   306|                        and g.iloc[idx - 4]
   307|                        and z.iloc[idx - 4] > z.iloc[idx - 3] > z.iloc[idx - 2] > z.iloc[idx - 1]
   308|                        and z.iloc[idx] >= z.iloc[idx - 1]
   309|                    )
   310|
   311|                if warn_overlap_only and not (b1 and brick):
   312|                    continue
   313|
   314|                if not (b1 or brick):
   315|                    continue
   316|
   317|                sigs.append(
   318|                    {
   319|                        "code": code,
   320|                        "name": r.name,
   321|                        "industry": r.industry,
   322|                        "signal_date": td,
   323|                        "next_date": str(next_row["trade_date"]),
   324|                        "signal_close": float(row["close"]),
   325|                        "next_open": float(next_row["open"]),
   326|                        "next_low": float(next_row["low"]),
   327|                        "b1": b1,
   328|                        "brick": brick,
   329|                        "j": float(safe_num(row.get("kdj_j"))) if pd.notna(safe_num(row.get("kdj_j"))) else 999,
   330|                    }
   331|                )
   332|
   333|        # 3) 排序 + 开仓
   334|        if can_open > 0 and sigs:
   335|            def _rank(s):
   336|                # 重合 > brick > b1
   337|                p = 0 if (s["b1"] and s["brick"]) else (1 if s["brick"] else 2)
   338|                return (p, s["j"])
   339|
   340|            sigs = sorted(sigs, key=_rank)
   341|            selected = sigs[: can_open * 2]  # 多看一点，避免不成交
   342|
   343|            opened = 0
   344|            for s in selected:
   345|                if opened >= can_open:
   346|                    break
   347|
   348|                if s["b1"] and s["brick"]:
   349|                    strategy = "B1_EXPERIMENTAL+BRICK_V3"
   350|                    buy_price = min(s["signal_close"] * 0.993, s["next_open"] * 0.988)
   351|                    hold_days = 1
   352|                elif s["brick"]:
   353|                    strategy = "BRICK_V3"
   354|                    buy_price = min(s["signal_close"] * 0.995, s["next_open"] * 0.99)
   355|                    hold_days = 1
   356|                else:
   357|                    strategy = "B1_EXPERIMENTAL"
   358|                    buy_price = min(s["signal_close"] * 0.993, s["next_open"] * 0.988)
   359|                    hold_days = B1_MAX_HOLD_DAYS
   360|
   361|                # 低吸成交判断
   362|                if s["next_low"] > buy_price:
   363|                    continue
   364|
   365|                # 单笔等权；若为B1类且信号日 avg5∈(1,2]，则轻降权到85%仓位
   366|                slots_left = max(1, can_open - opened)
   367|                budget = cash / slots_left
   368|                avg5_prev = omav_avg5_map.get(s["signal_date"])
   369|                deweight = False
   370|                # 先应用 V4-A：纯 B1 前两日弱结构过滤
   371|                if s["b1"] and (not s["brick"]):
   372|                    try:
   373|                        signal_idx = code_idx[s["code"]][s["signal_date"]]
   374|                        signal_df = code_data[s["code"]]
   375|                        prev1_pct = float(signal_df.iloc[signal_idx - 1].get("pct_chg", 0.0)) if signal_idx >= 1 else 0.0
   376|                        prev2_pct = float(signal_df.iloc[signal_idx - 2].get("pct_chg", 0.0)) if signal_idx >= 2 else 0.0
   377|                    except Exception:
   378|                        prev1_pct = 0.0
   379|                        prev2_pct = 0.0
   380|                    if (prev1_pct <= -1.0) and (prev2_pct <= -1.5):
   381|                        continue
   382|                    white_line = float(signal_df.iloc[signal_idx].get("white_line", 0.0) or 0.0)
   383|                    yellow_line = float(signal_df.iloc[signal_idx].get("yellow_line", 0.0) or 0.0)
   384|                    close_px = float(signal_df.iloc[signal_idx].get("close", 0.0) or 0.0)
   385|                    if white_line > 0 and yellow_line > 0:
   386|                        close_white_ratio = close_px / white_line
   387|                        white_yellow_ratio = white_line / yellow_line
   388|                        # 窄修正：过滤掉“白线明显压着收盘、且白黄线张口过大”的纯 B1 弱结构单
   389|                        if (close_white_ratio < 0.96) and (white_yellow_ratio > 1.09):
   390|                            continue
   391|
   392|                if (s["b1"] and (not s["brick"])) or (s["b1"] and s["brick"]):
   393|                    if avg5_prev is not None:
   394|                        try:
   395|                            avg5_prev = float(avg5_prev)
   396|                            if 1 < avg5_prev <= 2 and not (s["b1"] and s["brick"]):
   397|                                budget *= 0.5
   398|                                deweight = True
   399|                        except Exception:
   400|                            pass
   401|                shares = int(budget // buy_price // LOT_SIZE) * LOT_SIZE
   402|                if shares <= 0:
   403|                    continue
   404|
   405|                fee = _buy_fee(buy_price, shares)
   406|                cost = buy_price * shares + fee
   407|                if cost > cash:
   408|                    continue
   409|
   410|                cash -= cost
   411|                positions.append(
   412|                    Position(
   413|                        code=s["code"],
   414|                        name=s["name"],
   415|                        industry=s["industry"],
   416|                        strategy=strategy,
   417|                        buy_date=s["next_date"],
   418|                        buy_price=buy_price,
   419|                        shares=shares,
   420|                        hold_days=hold_days,
   421|                        initial_shares=shares,
   422|                    )
   423|                )
   424|                opened += 1
   425|
   426|        # 4) 记录当日净值（按收盘估值）
   427|        mv = 0.0
   428|        for p in positions:
   429|            idx_map = code_idx.get(p.code, {})
   430|            if td in idx_map:
   431|                px = float(code_data[p.code].iloc[idx_map[td]]["close"])
   432|                mv += px * p.shares
   433|            else:
   434|                mv += p.buy_price * p.shares
   435|
   436|        current_processed = len(nav_rows) + 1
   437|        if current_processed % 20 == 0 or current_processed == len(cal):
   438|            save_progress("running", current_processed, len(cal), f"processing {td}")
   439|
   440|        nav_rows.append(
   441|            {
   442|                "trade_date": td,
   443|                "cash": round(cash, 2),
   444|                "market_value": round(mv, 2),
   445|                "total_equity": round(cash + mv, 2),
   446|                "positions": len(positions),
   447|            }
   448|        )
   449|
   450|    nav = pd.DataFrame(nav_rows)
   451|    trades_df = pd.DataFrame(trades)
   452|
   453|    final_equity = float(nav.iloc[-1]["total_equity"]) if not nav.empty else INITIAL_CAPITAL
   454|    total_return = (final_equity / INITIAL_CAPITAL - 1) * 100
   455|
   456|    summary = {
   457|        "start_date": START_DATE,
   458|        "end_date": END_DATE,
   459|        "initial_capital": INITIAL_CAPITAL,
   460|        "final_equity": round(final_equity, 2),
   461|        "total_return_pct": round(total_return, 2),
   462|        "trade_count": int(len(trades_df)),
   463|        "win_rate_pct": round(float((trades_df["net_pnl"] > 0).mean() * 100), 2) if not trades_df.empty else 0.0,
   464|        "nav_path": str(OUT / "sim_replay_20230101_b1_experimental_v1_strict_brick_v3_v4a_plus_avg5_band_1_2_deweight_05_narrowfix_v1_nav.csv"),
   465|        "trades_path": str(OUT / "sim_replay_20230101_b1_experimental_v1_strict_brick_v3_v4a_plus_avg5_band_1_2_deweight_05_narrowfix_v1_trades.csv"),
   466|    }
   467|
   468|    nav.to_csv(OUT / "sim_replay_20230101_b1_experimental_v1_strict_brick_v3_v4a_plus_avg5_band_1_2_deweight_05_narrowfix_v1_nav.csv", index=False, encoding="utf-8-sig")
   469|    trades_df.to_csv(OUT / "sim_replay_20230101_b1_experimental_v1_strict_brick_v3_v4a_plus_avg5_band_1_2_deweight_05_narrowfix_v1_trades.csv", index=False, encoding="utf-8-sig")
   470|    (OUT / "sim_replay_20230101_b1_experimental_v1_strict_brick_v3_v4a_plus_avg5_band_1_2_deweight_05_narrowfix_v1_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
   471|
   472|    save_progress("done", len(cal), len(cal), "finished")
   473|    print(json.dumps(summary, ensure_ascii=False, indent=2))
   474|    try:
   475|        PROGRESS_PATH.unlink()
   476|    except Exception:
   477|        pass
   478|
   479|
   480|if __name__ == "__main__":
   481|    main()
   482|