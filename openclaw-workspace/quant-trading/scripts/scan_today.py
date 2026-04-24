#!/usr/bin/env python3
"""临时扫描脚本 - 基于scan_candidates.py，更新日期和持仓"""
import sys
import json
import os
from datetime import datetime

sys.path.insert(0, str(os.path.dirname(__file__) + "/.."))

import pandas as pd
from pathlib import Path
from quant.sim_replay_common import (
    load_universe, prepare_code_df, V4_EXCLUDED_INDUSTRIES, DATA,
    build_prepared_universe,
)
from quant.b1_experimental_v1 import b1_experimental_v1_ok

ROOT = Path(__file__).resolve().parents[1]
TRADE_DATE = "20260424"
START_DATE = "20250101"
PRICE_MIN = 3.0
PRICE_MAX = 300.0
MIN_SCORE = 3.0

T0 = {"AI算力", "半导体", "芯片", "AIDC", "人工智能", "IT设备", "通信设备", "软件服务", "互联网"}
T1 = {"光伏", "储能", "新能源", "电气仪表", "化工原料", "化肥农药"}
T2 = {"有色", "通信", "电力", "矿物制品", "新材料"}

# 当前持仓 - 排除
HELD_CODES = {"601222.SH", "603803.SH", "002821.SZ", "002805.SZ"}

V4A_PREV1_MAX = -1.0
V4A_PREV2_MAX = -1.5


def log(msg):
    print(msg, file=sys.stderr)


def sector_tier(industry):
    if industry in T0: return 0
    if industry in T1: return 1
    if industry in T2: return 2
    return 3


def tier_label(tier):
    return {0: "T0主线", 1: "T1支线", 2: "T2", 3: "其他"}.get(tier, "??")


def identify_candle(df):
    if len(df) < 3:
        return "数据不足"
    c = float(df["close"].iloc[-1])
    o = float(df["open"].iloc[-1])
    h = float(df["high"].iloc[-1])
    l = float(df["low"].iloc[-1])
    prev_c = float(df["close"].iloc[-2])
    prev_o = float(df["open"].iloc[-2])
    body = abs(c - o)
    full_range = h - l
    if full_range == 0:
        return "十字星"
    upper_shadow = h - max(c, o)
    lower_shadow = min(c, o) - l
    body_ratio = body / full_range
    if lower_shadow >= 2 * body and upper_shadow < body * 0.5 and body_ratio < 0.5:
        return "锤子线"
    if upper_shadow >= 2 * body and lower_shadow < body * 0.5 and body_ratio < 0.5:
        return "倒锤子线"
    if prev_c < prev_o and c > o and c > prev_o and o < prev_c:
        return "看涨吞没"
    if prev_c > prev_o and c < o and c < prev_o and o > prev_c:
        return "看跌吞没"
    if len(df) >= 3:
        c0 = float(df["close"].iloc[-3])
        o0 = float(df["open"].iloc[-3])
        c1 = float(df["close"].iloc[-2])
        o1 = float(df["open"].iloc[-2])
        day0_bear = (o0 > c0) and (abs(o0 - c0) / c0 > 0.015)
        day1_small = abs(c1 - o1) / max(c1, o1, 0.01) < 0.01
        day2_bull = (c > o) and (body_ratio > 0.5)
        gap_down = min(o1, c1) < c0
        if day0_bear and day1_small and day2_bull and gap_down:
            return "启明星"
    pct = 0
    try: pct = float(df["pct_chg"].iloc[-1])
    except: pass
    if c > o and body_ratio > 0.7 and pct > 3:
        return "大阳线"
    if c > o and body_ratio > 0.3:
        return "阳线"
    if c < o and body_ratio > 0.3:
        return "阴线"
    if body_ratio < 0.1:
        return "十字星"
    if lower_shadow > 3 * body and upper_shadow < body:
        return "蜻蜓十字"
    return "普通K线"


def scan():
    log("=" * 60)
    log("全市场候选票扫描 (0422)")
    log("=" * 60)

    meta = load_universe(DATA, excluded_industries=V4_EXCLUDED_INDUSTRIES)
    meta = meta[~meta["ts_code"].isin(HELD_CODES)].copy()
    # 排除科创板688
    meta = meta[~meta["ts_code"].str.startswith("688", na=False)].copy()
    # 排除ST
    meta = meta[~meta["name"].str.contains("ST", na=False)].copy()
    log("[STEP1] Universe: %d 只" % len(meta))

    log("[STEP2] 构建板块轮动Top5...")
    _, code_data, code_idx, rotation_map = build_prepared_universe(
        START_DATE, TRADE_DATE, DATA,
        excluded_industries=V4_EXCLUDED_INDUSTRIES,
    )
    log("[STEP2] 轮动Top5: %d 条记录" % len(rotation_map))

    # 看看今天有哪些行业在Top5
    today_top5 = [k for k in rotation_map if k[0] == TRADE_DATE]
    if today_top5:
        log("[STEP2] 今日Top5行业: %s" % ", ".join(set(k[1] for k in today_top5)))

    log("[STEP3] 逐股扫描...")
    results = []
    total = len(meta)
    errors = 0
    b1_count = 0
    brick_count = 0
    resonance_count = 0

    for i, row in enumerate(meta.itertuples(index=False), 1):
        code = row.ts_code
        name = row.name
        industry = row.industry

        if i % 500 == 0:
            log("[PROGRESS] %d/%d | cands=%d B1=%d brick=%d res=%d err=%d" % (
                i, total, len(results), b1_count, brick_count, resonance_count, errors))

        try:
            if code in code_data:
                df = code_data[code]
            else:
                continue

            if df is None or len(df) < 160:
                continue

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            if str(latest.get("trade_date", "")) != TRADE_DATE:
                continue

            close = float(latest.get("close", 0))
            pct_chg = float(latest.get("pct_chg", 0))
            if close <= PRICE_MIN or close > PRICE_MAX:
                continue

            # B1
            b1_v1 = b1_experimental_v1_ok(df)
            b1_v4a_filtered = False
            if b1_v1 and len(df) >= 3:
                prev1_pct = float(prev.get("pct_chg", 0))
                prev2_pct = float(df.iloc[-3].get("pct_chg", 0))
                if prev1_pct <= V4A_PREV1_MAX and prev2_pct <= V4A_PREV2_MAX:
                    b1_v4a_filtered = True
            b1_valid = b1_v1 and not b1_v4a_filtered

            # 砖型图
            brick_raw_turn_red = bool(latest.get("brick_raw_turn_red", False))
            brick_history_ok = bool(latest.get("brick_history_ok", False))
            white = float(latest.get("white_line", 0))
            yellow = float(latest.get("yellow_line", 0))
            high = float(latest.get("high", 0))

            white_above_yellow = (white > 0 and yellow > 0 and white > yellow)
            high_above_white = (high >= white * 0.99)
            in_rotation_top5 = rotation_map.get((TRADE_DATE, industry), False)

            brick_valid = (
                brick_raw_turn_red
                and brick_history_ok
                and white_above_yellow
                and high_above_white
                and in_rotation_top5
            )

            is_resonance = b1_valid and brick_valid

            if not b1_valid and not brick_valid:
                continue

            if b1_valid: b1_count += 1
            if brick_valid: brick_count += 1
            if is_resonance: resonance_count += 1

            # 评分
            score = 0.0
            tags = []
            b1_tag = "-"
            brick_tag = "-"

            if b1_valid:
                score += 3.0
                tags.append("B1(V1+V4-A)")
                b1_tag = "V1+V4-A通过"

            if brick_valid:
                score += 3.0
                tags.append("砖型图V3")
                brick_value = float(latest.get("brick_formula_value", 0))
                brick_tag = "V3通过(砖值=%.1f)" % brick_value
                brick_a = bool(latest.get("brick_a_group_ok", False))
                if brick_a:
                    score += 1.0
                    brick_tag += "+A组"
                brick_b = bool(latest.get("brick_b_group_ok", False))
                if brick_b:
                    score += 0.5
                    brick_tag += "+B组"

            if is_resonance:
                score += 2.0
                tags.append("共振单")

            vol = float(latest.get("vol", 0))
            prev_vol = float(prev.get("vol", 0))
            if prev_vol > 0 and vol > prev_vol * 1.3:
                score += 1.0
                tags.append("放量")
            if pct_chg > 3:
                score += 0.5
                tags.append("强涨(>3%)")

            if white_above_yellow and close >= white:
                score += 0.5
                tags.append("多头排列")

            dif = float(latest.get("macd_dif", 0))
            if dif > 0:
                score += 0.5

            tier = sector_tier(industry)
            if tier == 0:
                score += 1.5
                tags.append("T0主线")
            elif tier == 1:
                score += 1.0
                tags.append("T1支线")
            elif tier == 2:
                score += 0.5
                tags.append("T2")

            if score < MIN_SCORE:
                continue

            candle_pattern = identify_candle(df)
            stop_profit = round(close * 1.08, 2)
            stop_loss = round(close * 0.96, 2)
            yellow_stop = round(yellow, 2)

            # J值（KDJ）
            j_val = float(latest.get("kdj_j", 0))

            results.append({
                "name": name,
                "ts_code": code,
                "industry": industry,
                "close": close,
                "pct_chg": round(pct_chg, 2),
                "score": round(score, 1),
                "tier": tier,
                "tier_label": tier_label(tier),
                "b1_tag": b1_tag,
                "brick_tag": brick_tag,
                "tags": tags,
                "candle": candle_pattern,
                "white": round(white, 2),
                "yellow": round(yellow, 2),
                "j_val": round(j_val, 1),
                "stop_profit": stop_profit,
                "stop_loss": stop_loss,
                "yellow_stop": yellow_stop,
                "is_resonance": is_resonance,
                "rotation_top5": in_rotation_top5,
            })
        except Exception as e:
            errors += 1
            if errors <= 10:
                log("[ERROR] %s %s: %s" % (code, name, str(e)))
            continue

    log("")
    log("=" * 60)
    log("扫描完成!")
    log("  总扫描: %d" % total)
    log("  候选数: %d (score >= %.1f)" % (len(results), MIN_SCORE))
    log("  B1命中: %d" % b1_count)
    log("  砖型图命中: %d" % brick_count)
    log("  共振单: %d" % resonance_count)
    log("  错误: %d" % errors)
    log("=" * 60)

    # 排序: 共振 > 砖型图 > B1; 同级J从小到大
    # BaseLine优先级: 共振(0) > 砖型图(1) > B1(2)
    def sort_key(x):
        if x["is_resonance"]:
            sig_prio = 0
        elif "砖型图V3" in x["tags"]:
            sig_prio = 1
        else:
            sig_prio = 2
        return (sig_prio, x["tier"], -x["score"], x["j_val"])

    results.sort(key=sort_key)

    # 输出可读结果到stdout
    print("=== 候选票扫描结果 (2026-04-22) ===")
    print("OMAV状态: warn (5日滚动6.96) | 每日新开上限=1只")
    print("当前持仓: 3只A股 | 可开仓位: min(1, 3-3)=0 (已满)")
    print()
    print(f"总扫描: {total} | 候选: {len(results)} | B1: {b1_count} | 砖型图: {brick_count} | 共振: {resonance_count}")
    print()

    if not results:
        print("⚠ 今日无候选票通过扫描门槛")
    else:
        # 按类型分组输出
        resonance = [r for r in results if r["is_resonance"]]
        bricks = [r for r in results if not r["is_resonance"] and "砖型图V3" in r["tags"]]
        b1s = [r for r in results if not r["is_resonance"] and "砖型图V3" not in r["tags"]]

        if resonance:
            print(f"【共振单】({len(resonance)}只)")
            for r in resonance:
                print(f"  ★ {r['ts_code']} {r['name']} | {r['industry']} | {r['tier_label']}")
                print(f"    收盘{r['close']} 涨跌{r['pct_chg']:+.2f}% J={r['j_val']} 评分{r['score']}")
                print(f"    蜡烛图:{r['candle']} 白线{r['white']} 黄线{r['yellow']}")
                print(f"    止盈{r['stop_profit']} 止损{r['stop_loss']} 黄线止损{r['yellow_stop']}")
                print(f"    标签: {', '.join(r['tags'])}")
                print()

        if bricks:
            print(f"【砖型图】({len(bricks)}只)")
            for r in bricks:
                print(f"  ■ {r['ts_code']} {r['name']} | {r['industry']} | {r['tier_label']}")
                print(f"    收盘{r['close']} 涨跌{r['pct_chg']:+.2f}% J={r['j_val']} 评分{r['score']}")
                print(f"    蜡烛图:{r['candle']} 白线{r['white']} 黄线{r['yellow']}")
                print(f"    止盈{r['stop_profit']} 止损{r['stop_loss']} 黄线止损{r['yellow_stop']}")
                print(f"    标签: {', '.join(r['tags'])}")
                print()

        if b1s:
            print(f"【B1信号】({len(b1s)}只)")
            for r in b1s:
                print(f"  ● {r['ts_code']} {r['name']} | {r['industry']} | {r['tier_label']}")
                print(f"    收盘{r['close']} 涨跌{r['pct_chg']:+.2f}% J={r['j_val']} 评分{r['score']}")
                print(f"    蜡烛图:{r['candle']} 白线{r['white']} 黄线{r['yellow']}")
                print(f"    止盈TP1={round(r['close']*1.1,2)} TP2={round(r['close']*1.2,2)} 黄线止损{r['yellow_stop']}")
                print(f"    标签: {', '.join(r['tags'])}")
                print()

    # JSON也写文件
    output_file = ROOT / "outputs" / "scan" / f"scan_{TRADE_DATE}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({"stats": {
            "scan_date": TRADE_DATE,
            "total_scanned": total,
            "candidates": len(results),
            "b1_count": b1_count,
            "brick_count": brick_count,
            "resonance_count": resonance_count,
            "errors": errors,
            "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }, "candidates": results}, f, ensure_ascii=False, indent=2)
    log("[OUTPUT] JSON: %s" % output_file)


if __name__ == "__main__":
    scan()
