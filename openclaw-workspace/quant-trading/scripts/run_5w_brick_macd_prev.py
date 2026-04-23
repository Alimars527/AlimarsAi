#!/usr/bin/env python3
"""
砖型图 + 高级MACD组合策略
三个版本：
- prev: 砖型图XG当日 + 前一日MACD红柱 → 当日收盘买入
- same: 砖型图XG当日 + 当日MACD红柱 → 当日收盘买入
- next: 砖型图XG当日 + 后一日MACD红柱 → 后一日收盘买入

卖出规则：
- +10% 卖一半
- +20% 全走
- 成本价-5%止损
- 最多持有15天
"""

from __future__ import annotations
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quant.sim_replay_common import (
    build_prepared_universe,
    load_omav,
    load_trade_calendar,
    load_universe,
    prepare_code_df,
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
MAX_HOLD_DAYS = 15
TP1 = 0.10
TP2 = 0.20
STOP_LOSS = 0.05  # 成本价-5%

# 通过环境变量或修改此行切换版本: "prev" | "same" | "next"
MACD_TIMING = "prev"
VERSION_TAG = f"brick_macd_{MACD_TIMING}"
PROGRESS_PATH = OUT / f"sim_replay_20230101_{VERSION_TAG}_progress.json"


@dataclass
class Position:
    code: str
    name: str
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


def save_progress(status: str, processed: int = 0, total: int = 0, message: str = ""):
    progress = {
        "task": VERSION_TAG,
        "version": VERSION_TAG,
        "status": status,
        "processed": processed,
        "total": total,
        "progress_pct": round(100 * processed / total, 1) if total else 0,
        "message": message,
        "timestamp": str(pd.Timestamp.now()),
    }
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, ensure_ascii=False))


def calc_brick_xg(df: pd.DataFrame, idx: int) -> bool:
    """计算砖型图XG信号：由降转升"""
    if idx < 6:
        return False
    
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    
    # VAR1A:=(HHV(HIGH,4)-CLOSE)/(HHV(HIGH,4)-LLV(LOW,4))*100-90;
    # VAR2A:=SMA(VAR1A,4,1)+100;
    # VAR3A:=(CLOSE-LLV(LOW,4))/(HHV(HIGH,4)-LLV(LOW,4))*100;
    # VAR4A:=SMA(VAR3A,6,1);
    # VAR5A:=SMA(VAR4A,6,1)+100;
    # VAR6A:=VAR5A-VAR2A;
    # 砖型图:IF(VAR6A>4,VAR6A-4,0)
    # AA:=(REF(砖型图,1)<砖型图);
    # CC:=REF(AA,1)=0 AND (AA=1);
    # XG:CC>0
    
    # 预计算砖型图序列
    n = len(df)
    brick_vals = []
    for i in range(n):
        if i < 3:
            brick_vals.append(0)
            continue
        hhv4 = high[i-3:i+1].max()
        llv4 = low[i-3:i+1].min()
        if hhv4 == llv4:
            brick_vals.append(0)
            continue
        var1a = (hhv4 - close[i]) / (hhv4 - llv4) * 100 - 90
        brick_vals.append(max(0, var1a))
    
    # SMA(VAR1A,4,1) 和 SMA(VAR3A,6,1) 需要完整序列
    # 为了简化，我们直接用价格数据判断趋势转折
    # XG的核心是：前一日砖型图下降，当日砖型图上升
    
    # 实际计算
    var1a_arr = np.zeros(n)
    var2a_arr = np.zeros(n)
    var3a_arr = np.zeros(n)
    var4a_arr = np.zeros(n)
    var5a_arr = np.zeros(n)
    var6a_arr = np.zeros(n)
    brick_arr = np.zeros(n)
    
    for i in range(n):
        if i < 3:
            continue
        hhv4 = high[i-3:i+1].max()
        llv4 = low[i-3:i+1].min()
        if hhv4 == llv4:
            continue
        var1a = (hhv4 - close[i]) / (hhv4 - llv4) * 100 - 90
        var3a = (close[i] - llv4) / (hhv4 - llv4) * 100
        var1a_arr[i] = var1a
        var3a_arr[i] = var3a
    
    # SMA_CN(var1a, 4, 1)
    prev = None
    for i in range(n):
        if prev is None:
            prev = var1a_arr[i]
        else:
            prev = (1 * var1a_arr[i] + (4 - 1) * prev) / 4
        var2a_arr[i] = prev + 100
    
    # SMA_CN(var3a, 6, 1)
    prev = None
    for i in range(n):
        if prev is None:
            prev = var3a_arr[i]
        else:
            prev = (1 * var3a_arr[i] + (6 - 1) * prev) / 6
        var4a_arr[i] = prev
    
    # SMA_CN(var4a, 6, 1)
    prev = None
    for i in range(n):
        if prev is None:
            prev = var4a_arr[i]
        else:
            prev = (1 * var4a_arr[i] + (6 - 1) * prev) / 6
        var5a_arr[i] = prev + 100
    
    var6a_arr = var5a_arr - var2a_arr
    for i in range(n):
        if var6a_arr[i] > 4:
            brick_arr[i] = var6a_arr[i] - 4
    
    # AA = REF(砖型图,1) < 砖型图
    # CC = REF(AA,1) = 0 AND AA = 1
    # XG = CC > 0
    aa = idx >= 1 and brick_arr[idx-1] < brick_arr[idx]
    aa_prev = idx >= 2 and brick_arr[idx-2] < brick_arr[idx-1]
    cc = (not aa_prev) and aa
    return cc


def calc_macd_red_bar(df: pd.DataFrame, idx: int) -> bool:
    """计算高级MACD空心红柱：DIFF上穿0轴"""
    if idx < 30:
        return False
    
    close = df["close"].values
    
    # EMA(CLOSE,12) 和 EMA(CLOSE,26)
    ema12 = pd.Series(close).ewm(span=12, adjust=False).mean().values
    ema26 = pd.Series(close).ewm(span=26, adjust=False).mean().values
    diff = ema12 - ema26
    dea = pd.Series(diff).ewm(span=9, adjust=False).mean().values
    macd = 2 * (diff - dea)
    
    # CROSS(DIFF,0): 前一日DIFF<0，当日DIFF>=0
    if idx >= 1:
        return diff[idx-1] < 0 and diff[idx] >= 0
    return False


def main():
    save_progress("running", 0, 1, "preparing universe")
    meta = load_universe()
    meta = meta[meta["ts_code"].notna()].reset_index(drop=True)
    print(f"[INFO] preparing universe: {len(meta)}")
    
    meta = build_prepared_universe(meta, end_date=END_DATE)
    meta = meta[meta["list_date"].notna()].reset_index(drop=True)
    
    code_data: Dict[str, pd.DataFrame] = {}
    code_idx: Dict[str, Dict[str, int]] = {}
    for _, r in meta.iterrows():
        code = r["ts_code"]
        df = prepare_code_df(code, DATA)
        if df is None or len(df) < 50:
            continue
        code_data[code] = df
        code_idx[code] = {str(d): i for i, d in enumerate(df["trade_date"])}
    
    print(f"[INFO] usable codes: {len(code_data)}")
    
    cal = load_trade_calendar(START_DATE, END_DATE, DATA)
    cal_set = set(cal)
    
    positions: List[Position] = []
    cash = INITIAL_CAPITAL
    trades = []
    nav_rows = []
    
    tp1_count = 0
    tp2_count = 0
    sl_count = 0
    maxhold_count = 0
    
    for td in cal:
        # 1) 处理平仓
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
            
            # TP2: +20% 全走
            if not p.tp2_done and high >= p.buy_price * (1 + TP2):
                sell_price = p.buy_price * (1 + TP2)
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4),
                    "sell_price": round(sell_price, 4),
                    "shares": p.shares,
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "exit_reason": "tp2",
                })
                tp2_count += 1
                continue
            
            # TP1: +10% 卖一半
            if not p.tp1_done and high >= p.buy_price * (1 + TP1):
                sell_shares = p.shares // 2
                if sell_shares < LOT_SIZE:
                    sell_shares = p.shares
                sell_price = p.buy_price * (1 + TP1)
                fee = _sell_fee(sell_price, sell_shares)
                proceeds = sell_price * sell_shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4),
                    "sell_price": round(sell_price, 4),
                    "shares": sell_shares,
                    "net_pnl": round(proceeds - p.buy_price * sell_shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "exit_reason": "tp1_partial",
                })
                tp1_count += 1
                p.shares -= sell_shares
                p.tp1_done = True
                if p.shares <= 0:
                    continue
            
            # 止损: -5%
            if close <= p.buy_price * (1 - STOP_LOSS):
                sell_price = close
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4),
                    "sell_price": round(sell_price, 4),
                    "shares": p.shares,
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "exit_reason": "stop_loss",
                })
                sl_count += 1
                continue
            
            # 最大持有天数
            if held >= MAX_HOLD_DAYS:
                sell_price = close
                fee = _sell_fee(sell_price, p.shares)
                proceeds = sell_price * p.shares - fee
                cash += proceeds
                trades.append({
                    "code": p.code, "name": p.name,
                    "buy_date": p.buy_date, "sell_date": td,
                    "buy_price": round(p.buy_price, 4),
                    "sell_price": round(sell_price, 4),
                    "shares": p.shares,
                    "net_pnl": round(proceeds - p.buy_price * p.shares - _buy_fee(p.buy_price, p.initial_shares), 4),
                    "exit_reason": "max_hold",
                })
                maxhold_count += 1
                continue
            
            remain_positions.append(p)
        
        positions = remain_positions
        
        # 2) 生成信号并开仓
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
            if idx < 30 or idx + 1 >= len(df):
                continue
            
            row = df.iloc[idx]
            next_row = df.iloc[idx + 1]
            if str(next_row["trade_date"]) not in cal_set:
                continue
            
            # 检查砖型图XG
            brick_xg = calc_brick_xg(df, idx)
            if not brick_xg:
                continue
            
            # 检查MACD条件（根据版本不同）
            macd_ok = False
            buy_date = None
            buy_price = None
            
            if MACD_TIMING == "prev":
                # 前一日有MACD红柱 → 当日收盘买入
                if idx >= 1:
                    macd_ok = calc_macd_red_bar(df, idx - 1)
                if macd_ok:
                    buy_date = str(row["trade_date"])
                    buy_price = float(row["close"])
            
            elif MACD_TIMING == "same":
                # 当日有MACD红柱 → 当日收盘买入
                macd_ok = calc_macd_red_bar(df, idx)
                if macd_ok:
                    buy_date = str(row["trade_date"])
                    buy_price = float(row["close"])
            
            elif MACD_TIMING == "next":
                # 后一日有MACD红柱 → 后一日收盘买入
                if idx + 1 < len(df):
                    macd_ok = calc_macd_red_bar(df, idx + 1)
                if macd_ok:
                    buy_date = str(next_row["trade_date"])
                    buy_price = float(next_row["close"])
            
            if not macd_ok or buy_date is None:
                continue
            
            sigs.append({
                "code": code,
                "name": r.name,
                "signal_date": td,
                "buy_date": buy_date,
                "buy_price": buy_price,
            })
        
        # 3) 开仓（最多3只）
        can_open = max(0, 3 - len(positions))
        if can_open > 0 and sigs:
            # 随机排序（因为没有J值等排序因子）
            import random
            random.seed(42)
            random.shuffle(sigs)
            
            opened = 0
            for s in sigs:
                if opened >= can_open:
                    break
                
                slots_left = max(1, can_open - opened)
                budget = cash / slots_left
                shares = int(budget // s["buy_price"] // LOT_SIZE) * LOT_SIZE
                if shares <= 0:
                    continue
                
                fee = _buy_fee(s["buy_price"], shares)
                cost = s["buy_price"] * shares + fee
                if cost > cash:
                    continue
                
                cash -= cost
                positions.append(Position(
                    code=s["code"], name=s["name"],
                    buy_date=s["buy_date"], buy_price=s["buy_price"],
                    shares=shares, hold_days=MAX_HOLD_DAYS,
                    initial_shares=shares,
                ))
                opened += 1
        
        # 4) 记录净值
        mv = 0.0
        for p in positions:
            idx_map = code_idx.get(p.code, {})
            if td in idx_map:
                px = float(code_data[p.code].iloc[idx_map[td]]["close"])
                mv += px * p.shares
            else:
                mv += p.buy_price * p.shares
        
        nav_rows.append({"date": td, "nav": cash + mv})
        
        current_processed = len(nav_rows)
        if current_processed % 20 == 0 or current_processed == len(cal):
            save_progress("running", current_processed, len(cal), f"processing {td}")
    
    # 汇总
    nav = pd.DataFrame(nav_rows)
    trades_df = pd.DataFrame(trades)
    
    total_return_pct = round(100 * (cash + mv - INITIAL_CAPITAL) / INITIAL_CAPITAL, 2)
    max_dd = 0
    peak = nav["nav"].iloc[0]
    for v in nav["nav"]:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd
    
    years = (pd.to_datetime(END_DATE) - pd.to_datetime(START_DATE)).days / 365.25
    cagr_pct = round(100 * ((cash + mv) / INITIAL_CAPITAL) ** (1 / max(years, 0.1)) - 100, 2)
    
    summary = {
        "version": VERSION_TAG,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "initial_capital": INITIAL_CAPITAL,
        "final_equity": round(cash + mv, 2),
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": round(-100 * max_dd, 2),
        "trade_count": len(trades_df),
        "win_rate_pct": round(100 * (trades_df["net_pnl"] > 0).mean(), 2) if len(trades_df) else 0,
        "cagr_pct": cagr_pct,
        "tp1_count": tp1_count,
        "tp2_count": tp2_count,
        "sl_count": sl_count,
        "maxhold_count": maxhold_count,
    }
    
    print(f"\n{'='*50}")
    print(f"[{VERSION_TAG}] 回测完成")
    print(f"总收益: {total_return_pct}% | 笔数: {len(trades_df)} | 回撤: {round(-100*max_dd,2)}%")
    print(f"{'='*50}")
    
    nav.to_csv(OUT / f"sim_replay_20230101_{VERSION_TAG}_nav.csv", index=False)
    trades_df.to_csv(OUT / f"sim_replay_20230101_{VERSION_TAG}_trades.csv", index=False)
    (OUT / f"sim_replay_20230101_{VERSION_TAG}_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )
    save_progress("done", len(cal), len(cal), "completed")


if __name__ == "__main__":
    main()
