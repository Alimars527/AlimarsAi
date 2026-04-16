#!/usr/bin/env python3
"""
仓位评分集成脚本 — 接入模拟实盘 + 候选票推荐

用法:
  python scripts/score_candidates.py --date 20260416

功能:
  1. 加载当日扫描结果（scan_YYYYMMDD.json）
  2. 对每个候选票调用 position_scorer 打分
  3. 输出带评分和仓位建议的候选票列表（JSON + 表格）
  4. 模拟实盘模式：结合当前持仓和资金，给出具体买入建议
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.position_scorer import (
    score_candidate, ScoreResult, score_sector,
    SECTOR_TIERS, T0_KEYWORDS, T1_KEYWORDS, T2_KEYWORDS,
)
from quant.sim_replay_common import (
    load_universe, prepare_code_df, build_prepared_universe,
    DATA, V4_EXCLUDED_INDUSTRIES,
)
from quant.indicators import add_tactic_base_indicators

OUTPUT_DIR = ROOT / "outputs" / "scan"
CONFIG_DIR = ROOT / "config"

# V5-T1 排除行业
V5_EXCLUDED = V4_EXCLUDED_INDUSTRIES | {
    '化纤', '装修装饰', '其他商业', '焦炭加工',
}


def load_portfolio() -> dict:
    """加载模拟实盘配置"""
    p = CONFIG_DIR / "simulated_portfolio.yaml"
    if not p.exists():
        return {}
    import yaml
    with open(p, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_omav_value(date: str) -> Optional[float]:
    """获取指定日期的OMAV值"""
    omav_path = DATA / "omav" / "omav_daily_standardized_20260402.csv"
    if not omav_path.exists():
        return None
    df = pd.read_csv(omav_path, dtype={"trade_date": str})
    row = df[df["trade_date"] == date]
    if row.empty:
        return None
    return float(row.iloc[0].get("omav_value", 0))


def enrich_with_score(candidate: dict, df: pd.DataFrame,
                      omav_value: Optional[float] = None) -> dict:
    """对单个候选票进行评分"""
    close = candidate.get("close", 0)
    white = candidate.get("white", 0)
    yellow = candidate.get("yellow", 0)
    industry = candidate.get("industry", "")
    code = candidate.get("ts_code", "")
    name = candidate.get("name", "")

    # 从df获取技术指标
    if df is not None and len(df) >= 20:
        latest = df.iloc[-1]
        support = float(pd.to_numeric(df['low'].iloc[-10:], errors='coerce').min())

        # 均线
        close_s = pd.to_numeric(df['close'], errors='coerce')
        ma5 = float(close_s.rolling(5).mean().iloc[-1]) if len(df) >= 5 else None
        ma10 = float(close_s.rolling(10).mean().iloc[-1]) if len(df) >= 10 else None
        ma20 = float(close_s.rolling(20).mean().iloc[-1]) if len(df) >= 20 else None

        # 绿砖连续天数
        green_streak = int(latest.get("brick_green_streak", 0))

        # 信号判定
        brick_signal = bool(candidate.get("brick_tag", "-") != "-")
        b1_signal = bool(candidate.get("b1_tag", "-") != "-")

        result = score_candidate(
            code=code,
            name=name,
            industry=industry,
            close=close,
            white_line=white,
            yellow_line=yellow,
            df=df,
            idx=len(df) - 1,
            support=support,
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            brick_signal=brick_signal,
            b1_signal=b1_signal,
            green_streak=green_streak,
            omav_value=omav_value,
        )
    else:
        # 数据不足，用简化评分
        result = score_candidate(
            code=code, name=name, industry=industry,
            close=close, white_line=white, yellow_line=yellow,
            omav_value=omav_value,
        )

    return result


def generate_buy_advice(
    scored_candidates: List[tuple],  # (candidate_dict, ScoreResult)
    cash: float,
    current_holdings: List[dict],
    max_positions: int = 3,
    max_single_pct: float = 30.0,
    lot_size: int = 100,
) -> List[dict]:
    """
    根据评分和资金情况，生成具体买入建议
    """
    advice = []
    current_codes = {h.get("ts_code", h.get("code", "")) for h in current_holdings}
    slots_left = max(0, max_positions - len(current_holdings))

    if slots_left == 0:
        return advice

    # 按评分排序（高分优先）
    sorted_candidates = sorted(
        scored_candidates,
        key=lambda x: (x[1].total_score, x[0].get("score", 0)),
        reverse=True,
    )

    used_budget = 0.0
    total_equity = cash + sum(
        float(h.get("buy_price", 0)) * int(h.get("shares", 0))
        for h in current_holdings
    )

    for cand, result in sorted_candidates:
        if len(advice) >= slots_left:
            break
        if result.total_score <= 5:
            continue
        if cand.get("ts_code", "") in current_codes:
            continue

        # 仓位计算
        position_pct = result.adjusted_position_pct / 100.0
        budget = total_equity * position_pct
        buy_price = cand.get("close", 0) * 0.993  # 低吸价
        shares = int(budget // buy_price // lot_size) * lot_size
        cost = buy_price * shares + max(buy_price * shares * 0.000086, 5.0)

        if shares <= 0 or cost > cash - used_budget:
            continue

        advice.append({
            "code": cand.get("ts_code", ""),
            "name": cand.get("name", ""),
            "industry": cand.get("industry", ""),
            "score": result.total_score,
            "position_pct": result.adjusted_position_pct,
            "buy_price": round(buy_price, 2),
            "shares": shares,
            "estimated_cost": round(cost, 2),
            "score_details": {
                "rr": result.rr_score,
                "sector": result.sector_score,
                "trend": result.trend_score,
                "volume": result.volume_score,
                "signal": result.signal_score,
            },
            "tier": result.details.get("sector", {}).get("tier", "?"),
            "candle": cand.get("candle", ""),
            "white": cand.get("white", 0),
            "yellow": cand.get("yellow", 0),
            "tags": cand.get("tags", []),
        })
        used_budget += cost

    return advice


def format_table(scored: List[tuple], advice: List[dict]) -> str:
    """格式化输出表格"""
    lines = []

    # 评分表
    lines.append("╔══════════════════════════════════════════════════════════════╗")
    lines.append("║  仓位评分结果                                              ║")
    lines.append("╠══════════════════════════════════════════════════════════════╣")
    lines.append("║ {:<8} {:<8} {:<4} {:<4} {:<4} {:<4} {:<4} {:>4}  ║".format(
        "名称", "行业", "总分", "RR", "板块", "趋势", "量能", "仓位%"))
    lines.append("╠══════════════════════════════════════════════════════════════╣")

    for cand, result in scored:
        tier = result.details.get("sector", {}).get("tier", "?")
        name = cand.get("name", "")[:6]
        ind = cand.get("industry", "")[:4]
        lines.append("║ {:<8} {:<6}{:>2} {:>4.0f} {:>3.1f} {:>3.1f} {:>3.1f} {:>3.1f} {:>5.1f}% ║".format(
            name, ind, tier, result.total_score,
            result.rr_score, result.sector_score,
            result.trend_score, result.volume_score,
            result.adjusted_position_pct,
        ))

    lines.append("╚══════════════════════════════════════════════════════════════╝")

    # 买入建议
    if advice:
        lines.append("")
        lines.append("【买入建议】")
        for i, a in enumerate(advice, 1):
            lines.append(
                f"  Top{i}: {a['name']}({a['code']}) "
                f"得分={a['score']} 仓位={a['position_pct']}% "
                f"买价≈{a['buy_price']} {a['shares']}股 "
                f"≈{a['estimated_cost']}元"
            )
            lines.append(
                f"        板块={a['tier']} 形态={a['candle']} "
                f"RR={a['score_details']['rr']:.1f} "
                f"白={a['white']:.2f} 黄={a['yellow']:.2f}"
            )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="候选票仓位评分")
    parser.add_argument("--date", required=True, help="扫描日期 YYYYMMDD")
    parser.add_argument("--scan-file", help="直接指定scan JSON文件路径")
    parser.add_argument("--portfolio", action="store_true", help="生成模拟实盘买入建议")
    args = parser.parse_args()

    trade_date = args.date

    # 加载扫描结果
    if args.scan_file:
        scan_path = Path(args.scan_file)
    else:
        scan_path = OUTPUT_DIR / f"scan_{trade_date}.json"

    if not scan_path.exists():
        print(f"[ERROR] 扫描文件不存在: {scan_path}", file=sys.stderr)
        sys.exit(1)

    with open(scan_path, 'r', encoding='utf-8') as f:
        scan_data = json.load(f)

    candidates = scan_data.get("candidates", [])
    print(f"[INFO] 加载 {len(candidates)} 个候选票 (日期={trade_date})", file=sys.stderr)

    # 加载OMAV
    omav_value = load_omav_value(trade_date)
    print(f"[INFO] OMAV值: {omav_value}", file=sys.stderr)

    # 加载股票数据用于评分
    meta = load_universe(DATA, excluded_industries=V5_EXCLUDED)
    code_set = {c["ts_code"] for c in candidates}

    # 准备数据
    scored = []
    for i, cand in enumerate(candidates):
        code = cand.get("ts_code", "")
        if i % 20 == 0:
            print(f"[PROGRESS] 评分进度: {i}/{len(candidates)}", file=sys.stderr)

        try:
            # 尝试加载K线数据
            df = prepare_code_df(code, "20250101", trade_date, DATA)
            result = enrich_with_score(cand, df, omav_value)
            scored.append((cand, result))
        except Exception as e:
            print(f"[WARN] {code} 评分失败: {e}", file=sys.stderr)
            # 降级评分
            result = score_candidate(
                code=code, name=cand.get("name", ""),
                industry=cand.get("industry", ""),
                close=cand.get("close", 0),
                white_line=cand.get("white", 0),
                yellow_line=cand.get("yellow", 0),
                omav_value=omav_value,
            )
            scored.append((cand, result))

    # 按得分排序
    scored.sort(key=lambda x: x[1].total_score, reverse=True)

    # 生成买入建议
    advice = []
    if args.portfolio:
        portfolio = load_portfolio()
        cash = float(portfolio.get("portfolio", {}).get("current_cash", 50000))
        holdings = portfolio.get("portfolio", {}).get("holdings", [])
        max_pos = int(portfolio.get("meta", {}).get("rules", {}).get("max_positions", 3))
        max_single = float(portfolio.get("meta", {}).get("rules", {}).get("max_single_pct", 30))
        advice = generate_buy_advice(scored, cash, holdings, max_pos, max_single)

    # 输出表格
    print(format_table(scored, advice), file=sys.stderr)

    # 输出JSON到stdout
    output = {
        "trade_date": trade_date,
        "omav_value": omav_value,
        "scored_candidates": [
            {
                "ts_code": c.get("ts_code", ""),
                "name": c.get("name", ""),
                "industry": c.get("industry", ""),
                "close": c.get("close", 0),
                "old_score": c.get("score", 0),
                "position_score": r.total_score,
                "position_pct": r.adjusted_position_pct,
                "rr_score": r.rr_score,
                "sector_score": r.sector_score,
                "trend_score": r.trend_score,
                "volume_score": r.volume_score,
                "signal_score": r.signal_score,
                "tier": r.details.get("sector", {}).get("tier", "?"),
                "candle": c.get("candle", ""),
                "tags": c.get("tags", []),
            }
            for c, r in scored
        ],
        "buy_advice": advice,
    }

    # 写文件
    out_path = OUTPUT_DIR / f"scored_{trade_date}.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[INFO] 评分结果已写入: {out_path}", file=sys.stderr)

    # stdout输出JSON
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
