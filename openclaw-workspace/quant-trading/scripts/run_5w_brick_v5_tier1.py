     1|#!/usr/bin/env python3
     2|"""
     3|10w 模拟实盘节奏回放（砖型图 V5 Tier1扩展版）
     4|- 策略：BRICK_V5_T1（基于V4 + 额外4个Tier1行业硬黑名单）
     5|- 环境：OMAV 极致空头不新开仓；转弱降频
     6|- 执行：
     7|  * Brick: 买入价=min(C*0.995, next_open*0.99)，持有1天后卖出
     8|- 资金：10w 起步，A股100股一手
     9|- V5变更：在V4的10个排除行业基础上，增加4个Tier1亏损行业
    10|  * 化纤(4笔全亏, -11,447), 装修装饰(3笔, -8,706)
    11|  * 其他商业(3笔全亏, -8,643), 焦炭加工(2笔全亏, -5,680)
    12|  * 月度分析确认这些行业不是板块轮动主力，排除不影响轮动覆盖
    13|
    14|输出：
    15|- outputs/sim_replay_20230101_brick_v5_tier1_summary.json
    16|- outputs/sim_replay_20230101_brick_v5_tier1_trades.csv
    17|- outputs/sim_replay_20230101_brick_v5_tier1_nav.csv
    18|"""
    19|
    20|from __future__ import annotations
    21|import json
    22|import sys
    23|from dataclasses import dataclass
    24|from pathlib import Path
    25|from typing import Dict, List, Optional
    26|
    27|import pandas as pd
    28|
    29|ROOT = Path(__file__).resolve().parents[1]
    30|sys.path.insert(0, str(ROOT))
    31|DATA = ROOT / "data"
    32|OUT = ROOT / "outputs"
    33|
    34|START_DATE = "20230101"
    35|END_DATE = "20260403"
    36|INITIAL_CAPITAL = 50000.0
    37|LOT_SIZE = 100
    38|COMMISSION_RATE = 0.000086
    39|MIN_COMMISSION = 5.0
    40|STAMP_TAX_SELL = 0.0005
    41|RR_RATIO_MIN = 1.5
    42|B1_MAX_HOLD_DAYS = 10
    43|B1_WEAK_EXIT_PCT = 0.05
    44|B1_TP1 = 0.10
    45|B1_TP2 = 0.20
    46|
    47|
    48|@dataclass
    49|class Position:
    50|    code: str
    51|    name: str
    52|    industry: str
    53|    strategy: str  # B1_EXPERIMENTAL / BRICK_V3
    54|    buy_date: str
    55|    buy_price: float
    56|    shares: int
    57|    hold_days: int
    58|    initial_shares: int = 0
    59|    tp1_done: bool = False
    60|    tp2_done: bool = False
    61|
    62|
    63|def _commission(amount: float) -> float:
    64|    return max(amount * COMMISSION_RATE, MIN_COMMISSION)
    65|
    66|
    67|def _buy_fee(price: float, shares: int) -> float:
    68|    return _commission(price * shares)
    69|
    70|
    71|def _sell_fee(price: float, shares: int) -> float:
    72|    amount = price * shares
    73|    return _commission(amount) + amount * STAMP_TAX_SELL
    74|
    75|
    76|def j_threshold(td: str) -> float:
    77|    y = td[:4]
    78|    if y == "2023":
    79|        return -10
    80|    if y == "2024":
    81|        return 0
    82|    if y == "2025":
    83|        return 18
    84|    return 25
    85|
    86|
    87|def safe_num(v):
    88|    return pd.to_numeric(v, errors="coerce")
    89|
    90|
    91|def _sma_cn(series: pd.Series, n: int, m: int) -> pd.Series:
    92|    x = safe_num(series).fillna(0.0)
    93|    out = []
    94|    prev = None
    95|    for v in x.tolist():
    96|        if prev is None:
    97|            prev = v
    98|        else:
    99|            prev = (m * v + (n - m) * prev) / n
   100|        out.append(prev)
   101|    return pd.Series(out, index=series.index)
   102|
   103|
   104|def b1_experimental_ok(df: pd.DataFrame, idx: int) -> bool:
   105|    sub = df.iloc[: idx + 1].copy().reset_index(drop=True)
   106|    if len(sub) < 160:
   107|        return False
   108|    C = safe_num(sub['close'])
   109|    O = safe_num(sub['open'])
   110|    H = safe_num(sub['high'])
   111|    L = safe_num(sub['low'])
   112|    VOL = safe_num(sub['vol']).fillna(0.0)
   113|    REAL_YANG = (C > O) & ~(C < C.shift(1))
   114|    REAL_YIN = (C < O) & ~(C > C.shift(1))
   115|    ll9 = L.rolling(9).min(); hh9 = H.rolling(9).max()
   116|    RSV = (C - ll9) / (hh9 - ll9) * 100
   117|    K = _sma_cn(RSV, 3, 1)
   118|    D = _sma_cn(K, 3, 1)
   119|    J = 3 * K - 2 * D
   120|    J_OK = J <= 13
   121|    VOL_YANG1 = (VOL * REAL_YANG.astype(int)).rolling(57).sum()
   122|    VOL_YIN1 = (VOL * REAL_YIN.astype(int)).rolling(57).sum()
   123|    VOL_YANG2 = (VOL * REAL_YANG.astype(int)).rolling(14).sum()
   124|    VOL_YIN2 = (VOL * REAL_YIN.astype(int)).rolling(14).sum()
   125|    YANGYIN_OK1 = VOL_YANG1 > 1.25 * VOL_YIN1
   126|    YANGYIN_OK2 = VOL_YANG2 > 2.25 * VOL_YIN2
   127|    MV = safe_num(sub.get('total_mv_billion'))
   128|    MVOK = MV >= 50
   129|    O85 = O.rolling(21).min() + 0.95 * (O.rolling(21).max() - O.rolling(21).min())
   130|    TOP15O = O >= O85
   131|    FD15 = (C < C.shift(1)) & (C <= O) & (VOL >= 1.2 * VOL.shift(1))
   132|    CNT28 = ((TOP15O & FD15).astype(int)).rolling(21).sum()
   133|    GOOD28 = CNT28 <= 0
   134|    AVG40 = VOL.rolling(40).mean()
   135|    PLRY = (VOL > 1.95 * VOL.shift(1)) & (C > O) & (VOL > AVG40)
   136|    PLRY_CNT = (((PLRY.astype(int)).rolling(14).sum() >= 2) | ((PLRY.astype(int)).rolling(57).sum() >= 4))
   137|    prev_plry = PLRY.shift(1).eq(True)
   138|    PLRY_FIRST = PLRY & (~prev_plry)
   139|    PLRY_CONT = PLRY & prev_plry
   140|    prev_real_yin = REAL_YIN.shift(1).eq(True)
   141|    PRE_NOT_REALYIN = ~prev_real_yin
   142|    HALF_DOWN = PRE_NOT_REALYIN & (C < C.shift(1)) & (VOL <= 0.5 * VOL.shift(1))
   143|    CNT_FIRST = PLRY_FIRST.astype(int).rolling(57).sum()
   144|    CNT_CONT = PLRY_CONT.astype(int).rolling(57).sum()
   145|    CNT_HALF = HALF_DOWN.astype(int).rolling(57).sum()
   146|    THREE_SUM_OK = (CNT_FIRST + CNT_CONT + CNT_HALF) >= 4
   147|    MAXVOL28 = VOL.rolling(28).max()
   148|    MAX28_BAD = (VOL == MAXVOL28) & REAL_YIN
   149|    MAX28_OK = MAX28_BAD.astype(int).rolling(28).sum() == 0
   150|    A1 = ((PLRY_CNT & YANGYIN_OK1 & J_OK & MVOK & GOOD28 & THREE_SUM_OK & MAX28_OK) | (PLRY_CNT & YANGYIN_OK2 & J_OK & MVOK & GOOD28 & MAX28_OK))
   151|    HMSHORTWL = sub['white_line']
   152|    HMLONGYL = sub['yellow_line']
   153|    B1 = (HMSHORTWL >= HMLONGYL * 0.985) & (C >= HMLONGYL * 0.985) & A1
   154|    return bool(B1.iloc[-1])
   155|
   156|
   157|def load_omav() -> pd.DataFrame:
   158|    p = DATA / "omav" / "omav_daily_standardized_20260402.csv"
   159|    df = pd.read_csv(p, dtype={"trade_date": str})
   160|    df = df.sort_values("trade_date").reset_index(drop=True)
   161|    # 兜底：如果列不存在，就按规则临时计算
   162|    if "omav_rotation_warning_flag" not in df.columns:
   163|        df["omav_rotation_warning_flag"] = safe_num(df.get("omav_value")).fillna(0) <= -2.3
   164|    if "omav_bear_regime_flag" not in df.columns:
   165|        if "omav_5day_sum" in df.columns:
   166|            df["omav_bear_regime_flag"] = safe_num(df["omav_5day_sum"]).fillna(0) < -5
   167|        else:
   168|            v = safe_num(df.get("omav_value")).fillna(0)
   169|            df["omav_bear_regime_flag"] = v.rolling(5).sum() < -5
   170|    return df
   171|
   172|
   173|def load_trade_calendar() -> List[str]:
   174|    cal = pd.read_csv(DATA / "daily" / "000001.SZ.csv", dtype={"trade_date": str})[["trade_date"]]
   175|    cal = cal.drop_duplicates().sort_values("trade_date")
   176|    return [d for d in cal["trade_date"].tolist() if START_DATE <= d <= END_DATE]
   177|
   178|
   179|# Brick V5 Tier1 行业黑名单：V4的10个 + Tier1的4个
   180|EXCLUDED_INDUSTRIES = {
   181|    # === V4 原有10个行业 ===
   182|    '航空',       # 16 trades, PnL=-11,849, WR=43.8%
   183|    '电气设备',   # 16 trades, PnL=-7,985
   184|    '旅游服务',   # 5 trades, PnL=-7,805 (全亏)
   185|    '黄金',       # 17 trades, PnL=-7,730
   186|    '全国地产',   # 4 trades, PnL=-7,455, WR=0%
   187|    '轻工机械',   # PnL≈-6,000
   188|    '农药化肥',   # PnL≈-5,000
   189|    '石油贸易',   # PnL≈-4,800
   190|    '矿物制品',   # PnL≈-4,400
   191|    '专用机械',   # PnL≈-4,400
   192|    # === V5 Tier1 新增4个行业（总亏损-34,476, 12笔交易, WR 0-33%）===
   193|    '化纤',       # 4 trades, PnL=-11,447, WR=0%, 月度分析确认非轮动主力
   194|    '装修装饰',   # 3 trades, PnL=-8,706, WR=33%, 月度分析确认非轮动主力
   195|    '其他商业',   # 3 trades, PnL=-8,643, WR=0%, 月度分析确认非轮动主力
   196|    '焦炭加工',   # 2 trades, PnL=-5,680, WR=0%, 月度分析确认非轮动主力
   197|}
   198|
   199|
   200|def load_universe() -> pd.DataFrame:
   201|    meta = pd.read_csv(DATA / "meta" / "stock_basic.csv", dtype=str).fillna("")
   202|    meta = meta[~meta["ts_code"].str.endswith(".BJ")]
   203|    meta = meta[~meta["name"].str.upper().str.contains("ST", na=False)]
   204|    meta = meta[~meta["industry"].str.contains("房地产", na=False)]
   205|    meta = meta[meta["industry"] != "银行"]
   206|    # 当前口径：不做创业板
   207|    meta = meta[~meta["ts_code"].str.startswith("300")]
   208|    # 注意：此处不再排除EXCLUDED_INDUSTRIES，改为在rotation_map计算后过滤
   209|    # 这样确保rotation_map基于全量行业数据计算，不受排除列表影响
   210|    return meta[["ts_code", "name", "industry", "list_date"]].copy()
   211|
   212|
   213|def prepare_code_df(code: str) -> Optional[pd.DataFrame]:
   214|    from quant.indicators import add_tactic_base_indicators
   215|    from quant.brick_formula import add_brick_formula_flags
   216|
   217|    p_daily = DATA / "daily" / f"{code}.csv"
   218|    p_basic = DATA / "daily_basic" / f"{code}.csv"
   219|    if not p_daily.exists() or not p_basic.exists():
   220|        return None
   221|
   222|    try:
   223|        d = pd.read_csv(p_daily, dtype={"trade_date": str}).sort_values("trade_date").reset_index(drop=True)
   224|        b = pd.read_csv(p_basic, dtype={"trade_date": str})
   225|        if d.empty or "trade_date" not in d.columns:
   226|            return None
   227|
   228|        for c in ["open", "high", "low", "close", "vol", "pct_chg"]:
   229|            if c in d.columns:
   230|                d[c] = safe_num(d[c])
   231|
   232|        if "total_mv" in b.columns:
   233|            b = b[["trade_date", "total_mv"]].copy()
   234|            b["total_mv_billion"] = safe_num(b["total_mv"]) / 10000.0
   235|            d = d.merge(b[["trade_date", "total_mv_billion"]], on="trade_date", how="left")
   236|        else:
   237|            d["total_mv_billion"] = pd.NA
   238|
   239|        d = add_tactic_base_indicators(d)
   240|        d = add_brick_formula_flags(d)
   241|
   242|        # 需要列兜底
   243|        for c in ["brick_formula_green", "brick_raw_turn_red", "brick_history_ok"]:
   244|            if c not in d.columns:
   245|                d[c] = False
   246|        if "brick_formula_value" not in d.columns:
   247|            d["brick_formula_value"] = 0.0
   248|
   249|        d = d[(d["trade_date"] >= START_DATE) & (d["trade_date"] <= END_DATE)].copy()
   250|        if d.empty:
   251|            return None
   252|        return d.reset_index(drop=True)
   253|    except Exception:
   254|        return None
   255|
   256|
   257|def main():
   258|    OUT.mkdir(parents=True, exist_ok=True)
   259|
   260|    omav = load_omav()
   261|    omav_map = omav.set_index("trade_date").to_dict("index")
   262|    cal = load_trade_calendar()
   263|    cal_set = set(cal)
   264|
   265|    meta = load_universe()
   266|
   267|    code_data: Dict[str, pd.DataFrame] = {}
   268|    code_idx: Dict[str, Dict[str, int]] = {}
   269|    industry_daily_ret_rows = []
   270|
   271|    print(f"[INFO] preparing universe: {len(meta)}")
   272|    for r in meta.itertuples(index=False):
   273|        c = r.ts_code
   274|        df = prepare_code_df(c)
   275|        if df is None or len(df) < 40:
   276|            continue
   277|        code_data[c] = df
   278|        code_idx[c] = {td: i for i, td in enumerate(df["trade_date"].tolist())}
   279|        t = df[["trade_date", "pct_chg"]].copy()
   280|        t["industry"] = r.industry
   281|        industry_daily_ret_rows.append(t)
   282|
   283|    print(f"[INFO] usable codes: {len(code_data)}")
   284|
   285|    if not industry_daily_ret_rows:
   286|        raise RuntimeError("no usable codes")
   287|
   288|    ind_df = pd.concat(industry_daily_ret_rows, ignore_index=True)
   289|    ind_df["pct_chg"] = safe_num(ind_df["pct_chg"])
   290|    board = (
   291|        ind_df.groupby(["trade_date", "industry"], as_index=False)["pct_chg"]
   292|        .mean()
   293|        .sort_values(["trade_date", "pct_chg"], ascending=[True, False])
   294|    )
   295|    board["rank"] = board.groupby("trade_date")["pct_chg"].rank(method="first", ascending=False)
   296|    board_top5 = board[board["rank"] <= 5].copy()
   297|    rotation_map = board_top5.assign(flag=True).set_index(["trade_date", "industry"])["flag"].to_dict()
   298|
   299|    # rotation_map已基于全量行业数据计算，现在过滤掉排除行业的股票用于交易
   300|    trading_meta = meta[~meta["industry"].isin(EXCLUDED_INDUSTRIES)].copy()
   301|    print(f"[INFO] rotation_map from {len(meta)} stocks, trading universe: {len(trading_meta)} stocks (excluded {len(meta)-len(trading_meta)})")
   302|
   303|    cash = INITIAL_CAPITAL
   304|    positions: List[Position] = []
   305|    trades = []
   306|    nav_rows = []
   307|
   308|    for td in cal:
   309|        # 1) 先处理平仓（按收盘）
   310|        remain_positions = []
   311|        for p in positions:
   312|            idx_map = code_idx.get(p.code, {})
   313|            if td not in idx_map:
   314|                remain_positions.append(p)
   315|                continue
   316|            idx = idx_map[td]
   317|            df = code_data[p.code]
   318|            # 计算已持有交易日
   319|            buy_idx = idx_map.get(p.buy_date)
   320|            if buy_idx is None:
   321|                remain_positions.append(p)
   322|                continue
   323|            held = idx - buy_idx
   324|            if held < p.hold_days:
   325|                remain_positions.append(p)
   326|                continue
   327|
   328|            sell_price = float(df.iloc[idx]["close"])
   329|            fee = _sell_fee(sell_price, p.shares)
   330|            proceeds = sell_price * p.shares - fee
   331|            cash += proceeds
   332|            trades.append(
   333|                {
   334|                    "code": p.code,
   335|                    "name": p.name,
   336|                    "industry": p.industry,
   337|                    "strategy": p.strategy,
   338|                    "buy_date": p.buy_date,
   339|                    "sell_date": td,
   340|                    "buy_price": round(p.buy_price, 4),
   341|                    "sell_price": round(sell_price, 4),
   342|                    "shares": p.shares,
   343|                    "gross_pnl": round((sell_price - p.buy_price) * p.shares, 4),
   344|                    "fees": round(_buy_fee(p.buy_price, p.shares) + fee, 4),
   345|                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.shares), 4),
   346|                }
   347|            )
   348|
   349|        positions = remain_positions
   350|
   351|        # 2) 生成当日信号，并尝试在“下一交易日”按规则成交
   352|        # 环境控制
   353|        om = omav_map.get(td, {})
   354|        bear = str(om.get("omav_bear_regime_flag", "False")).lower() == "true"
   355|        warn = str(om.get("omav_rotation_warning_flag", "False")).lower() == "true"
   356|
   357|        max_new = 0 if bear else (1 if warn else 3)
   358|        max_total_pos = 1 if warn else 3
   359|        free_slots = max(0, max_total_pos - len(positions))
   360|        can_open = min(max_new, free_slots)
   361|        warn_overlap_only = bool(warn and not bear)
   362|
   363|        sigs = []
   364|        if can_open > 0:
   365|            for r in trading_meta.itertuples(index=False):
   366|                code = r.ts_code
   367|                if code not in code_data:
   368|                    continue
   369|                idx_map = code_idx[code]
   370|                if td not in idx_map:
   371|                    continue
   372|
   373|                idx = idx_map[td]
   374|                df = code_data[code]
   375|                if idx < 25 or idx + 1 >= len(df):
   376|                    continue
   377|
   378|                row = df.iloc[idx]
   379|                next_row = df.iloc[idx + 1]
   380|                if str(next_row["trade_date"]) not in cal_set:
   381|                    continue
   382|
   383|                b1 = b1_experimental_ok(df, idx)
   384|                # BRICK_V3
   385|                brick_v1 = bool(row.get("brick_raw_turn_red", False)) and bool(row.get("brick_history_ok", False))
   386|                brick = False
   387|                if brick_v1 and (not bear) and (not warn) and idx >= 4:
   388|                    z = safe_num(df["brick_formula_value"]).fillna(0)
   389|                    g = df["brick_formula_green"].fillna(False).astype(bool)
   390|                    white = safe_num(row.get("white_line"))
   391|                    yellow = safe_num(row.get("yellow_line"))
   392|                    high = safe_num(row.get("high"))
   393|                    rotation_ok = rotation_map.get((td, r.industry), False)
   394|                    brick = bool(
   395|                        rotation_ok
   396|                        and pd.notna(white)
   397|                        and pd.notna(yellow)
   398|                        and pd.notna(high)
   399|                        and high >= white
   400|                        and white > yellow
   401|                        and g.iloc[idx - 1]
   402|                        and g.iloc[idx - 2]
   403|                        and g.iloc[idx - 3]
   404|                        and g.iloc[idx - 4]
   405|                        and z.iloc[idx - 4] > z.iloc[idx - 3] > z.iloc[idx - 2] > z.iloc[idx - 1]
   406|                        and z.iloc[idx] >= z.iloc[idx - 1]
   407|                    )
   408|
   409|                b1 = False
   410|                if warn_overlap_only and not brick:
   411|                    continue
   412|
   413|                if not brick:
   414|                    continue
   415|
   416|                sigs.append(
   417|                    {
   418|                        "code": code,
   419|                        "name": r.name,
   420|                        "industry": r.industry,
   421|                        "signal_date": td,
   422|                        "next_date": str(next_row["trade_date"]),
   423|                        "signal_close": float(row["close"]),
   424|                        "next_open": float(next_row["open"]),
   425|                        "next_low": float(next_row["low"]),
   426|                        "b1": b1,
   427|                        "brick": brick,
   428|                        "j": float(safe_num(row.get("kdj_j"))) if pd.notna(safe_num(row.get("kdj_j"))) else 999,
   429|                    }
   430|                )
   431|
   432|        # 3) 排序 + 开仓
   433|        if can_open > 0 and sigs:
   434|            def _rank(s):
   435|                # 重合 > brick > b1
   436|                p = 0 if (s["b1"] and s["brick"]) else (1 if s["brick"] else 2)
   437|                return (p, s["j"])
   438|
   439|            sigs = sorted(sigs, key=_rank)
   440|            selected = sigs[: can_open * 2]  # 多看一点，避免不成交
   441|
   442|            opened = 0
   443|            for s in selected:
   444|                if opened >= can_open:
   445|                    break
   446|
   447|                strategy = "BRICK_V5_T1"
   448|                buy_price = min(s["signal_close"] * 0.995, s["next_open"] * 0.99)
   449|                hold_days = 1
   450|
   451|                # 低吸成交判断
   452|                if s["next_low"] > buy_price:
   453|                    continue
   454|
   455|                # 单笔等权
   456|                slots_left = max(1, can_open - opened)
   457|                budget = cash / slots_left
   458|                shares = int(budget // buy_price // LOT_SIZE) * LOT_SIZE
   459|                if shares <= 0:
   460|                    continue
   461|
   462|                fee = _buy_fee(buy_price, shares)
   463|                cost = buy_price * shares + fee
   464|                if cost > cash:
   465|                    continue
   466|
   467|                cash -= cost
   468|                positions.append(
   469|                    Position(
   470|                        code=s["code"],
   471|                        name=s["name"],
   472|                        industry=s["industry"],
   473|                        strategy=strategy,
   474|                        buy_date=s["next_date"],
   475|                        buy_price=buy_price,
   476|                        shares=shares,
   477|                        hold_days=hold_days,
   478|                        initial_shares=shares,
   479|                    )
   480|                )
   481|                opened += 1
   482|
   483|        # 4) 记录当日净值（按收盘估值）
   484|        mv = 0.0
   485|        for p in positions:
   486|            idx_map = code_idx.get(p.code, {})
   487|            if td in idx_map:
   488|                px = float(code_data[p.code].iloc[idx_map[td]]["close"])
   489|                mv += px * p.shares
   490|            else:
   491|                mv += p.buy_price * p.shares
   492|
   493|        nav_rows.append(
   494|            {
   495|                "trade_date": td,
   496|                "cash": round(cash, 2),
   497|                "market_value": round(mv, 2),
   498|                "total_equity": round(cash + mv, 2),
   499|                "positions": len(positions),
   500|            }
   501|        )
   502|
   503|    nav = pd.DataFrame(nav_rows)
   504|    trades_df = pd.DataFrame(trades)
   505|
   506|    final_equity = float(nav.iloc[-1]["total_equity"]) if not nav.empty else INITIAL_CAPITAL
   507|    total_return = (final_equity / INITIAL_CAPITAL - 1) * 100
   508|
   509|    summary = {
   510|        "start_date": START_DATE,
   511|        "end_date": END_DATE,
   512|        "initial_capital": INITIAL_CAPITAL,
   513|        "final_equity": round(final_equity, 2),
   514|        "total_return_pct": round(total_return, 2),
   515|        "trade_count": int(len(trades_df)),
   516|        "win_rate_pct": round(float((trades_df["net_pnl"] > 0).mean() * 100), 2) if not trades_df.empty else 0.0,
   517|        "nav_path": str(OUT / "sim_replay_20230101_brick_v5_tier1_nav.csv"),
   518|        "trades_path": str(OUT / "sim_replay_20230101_brick_v5_tier1_trades.csv"),
   519|    }
   520|
   521|    nav.to_csv(OUT / "sim_replay_20230101_brick_v5_tier1_nav.csv", index=False, encoding="utf-8-sig")
   522|    trades_df.to_csv(OUT / "sim_replay_20230101_brick_v5_tier1_trades.csv", index=False, encoding="utf-8-sig")
   523|    (OUT / "sim_replay_20230101_brick_v5_tier1_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
   524|
   525|    print(json.dumps(summary, ensure_ascii=False, indent=2))
   526|
   527|
   528|if __name__ == "__main__":
   529|    main()
   530|