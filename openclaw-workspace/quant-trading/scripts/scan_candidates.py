#!/usr/bin/env python3
"""全市场候选票扫描 V2 — 正确战法口径

B1: 实验版V1信号 + V4-A前两日结构过滤
砖型图: V3严格口径 (raw_turn_red + history_ok + 白>黄 + high>=白 + 轮动Top5)
共振单: B1 + 砖型图同时命中
OMAV: 当前数据至20260402，对0414扫描跳过OMAV过滤

输出: JSON写文件, 日志到stderr
"""
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
OUTPUT_DIR = ROOT / "outputs" / "scan"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 配置 ──────────────────────────────────────────────
TRADE_DATE = "20260414"
START_DATE = "20250101"  # prepare_code_df用此日期过滤，但底层csv有更长历史
PRICE_MIN = 3.0
PRICE_MAX = 300.0
MIN_SCORE = 3.0

# 板块优先级映射
T0 = {"AI算力", "半导体", "芯片", "AIDC", "人工智能", "IT设备", "通信设备", "软件服务", "互联网"}
T1 = {"光伏", "储能", "新能源", "电气仪表", "化工原料", "化肥农药"}
T2 = {"有色", "通信", "电力", "矿物制品", "新材料"}

# 已持仓 — 排除
HELD_CODES = {"002756.SZ", "002709.SZ", "159545.SZ", "603601.SH", "002294.SZ"}

# V4-A 前两日结构过滤阈值
V4A_PREV1_MAX = -1.0   # 前一日涨跌幅 <= -1.0% → 排除
V4A_PREV2_MAX = -1.5   # 前两日涨跌幅 <= -1.5% → 排除


def log(msg: str):
    print(msg, file=sys.stderr)


def sector_tier(industry: str) -> int:
    if industry in T0:
        return 0
    if industry in T1:
        return 1
    if industry in T2:
        return 2
    return 3


def tier_label(tier: int) -> str:
    return {0: "T0主线", 1: "T1支线", 2: "T2", 3: "其他"}.get(tier, "??")


def identify_candle(df: pd.DataFrame) -> str:
    """识别最近几日的蜡烛图形态"""
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

    # 锤子线：实体小，下影线>=2倍实体，上影线短
    if lower_shadow >= 2 * body and upper_shadow < body * 0.5 and body_ratio < 0.5:
        return "锤子线"

    # 倒锤子线
    if upper_shadow >= 2 * body and lower_shadow < body * 0.5 and body_ratio < 0.5:
        return "倒锤子线"

    # 看涨吞没：前阴后阳，阳线实体完全包住阴线实体
    if prev_c < prev_o and c > o and c > prev_o and o < prev_c:
        return "看涨吞没"

    # 看跌吞没
    if prev_c > prev_o and c < o and c < prev_o and o > prev_c:
        return "看跌吞没"

    # 启明星：前大阴 + 中间小实体（缺口低开）+ 后大阳
    if len(df) >= 3:
        c0 = float(df["close"].iloc[-3])
        o0 = float(df["open"].iloc[-3])
        c1 = float(df["close"].iloc[-2])
        o1 = float(df["open"].iloc[-2])
        # Day0大阴, Day1小实体且低开, Day2大阳
        day0_bear = (o0 > c0) and (abs(o0 - c0) / c0 > 0.015)
        day1_small = abs(c1 - o1) / max(c1, o1, 0.01) < 0.01 if max(c1, o1) > 0 else False
        day2_bull = (c > o) and (body_ratio > 0.5)
        gap_down = min(o1, c1) < c0  # Day1实体低于Day0收盘
        if day0_bear and day1_small and day2_bull and gap_down:
            return "启明星"

    # 大阳线
    pct = 0
    try:
        pct = float(df["pct_chg"].iloc[-1])
    except Exception:
        pass
    if c > o and body_ratio > 0.7 and pct > 3:
        return "大阳线"

    # 小阳线
    if c > o and body_ratio > 0.3:
        return "阳线"

    # 小阴线
    if c < o and body_ratio > 0.3:
        return "阴线"

    # 十字星
    if body_ratio < 0.1:
        return "十字星"

    # 蜻蜓十字（下影线长）
    if lower_shadow > 3 * body and upper_shadow < body:
        return "蜻蜓十字"

    return "普通K线"


def scan():
    log("=" * 60)
    log("全市场候选票扫描 V2 (战法口径)")
    log("扫描日期: %s" % TRADE_DATE)
    log("=" * 60)

    # ── Step 1: 加载universe ──
    meta = load_universe(DATA, excluded_industries=V4_EXCLUDED_INDUSTRIES)
    # 排除已持仓
    meta = meta[~meta["ts_code"].isin(HELD_CODES)].copy()
    log("[STEP1] Universe: %d 只 (V4黑名单+已持仓排除后)" % len(meta))

    # ── Step 2: 构建轮动Top5 ──
    log("[STEP2] 构建板块轮动Top5 (build_prepared_universe)...")
    # build_prepared_universe需要全历史数据来计算rotation_map
    # 我们用和prepare_code_df同样的日期范围
    _, code_data, code_idx, rotation_map = build_prepared_universe(
        START_DATE, TRADE_DATE, DATA,
        excluded_industries=V4_EXCLUDED_INDUSTRIES,
    )
    log("[STEP2] 轮动Top5: %d 条记录 (date+industry -> Top5)" % len(rotation_map))

    # ── Step 3: OMAV检查 ──
    omav_available = False
    omav_path = DATA / "omav" / "omav_daily_standardized_20260402.csv"
    if omav_path.exists():
        omav_df = pd.read_csv(omav_path, dtype={"trade_date": str})
        max_omav_date = omav_df["trade_date"].max()
        if max_omav_date >= TRADE_DATE:
            omav_available = True
            log("[OMAV] 数据可用, 最新日期: %s" % max_omav_date)
        else:
            log("[OMAV] 数据过期, 最新=%s, 需要=%s → 跳过OMAV过滤" % (max_omav_date, TRADE_DATE))
    else:
        log("[OMAV] 数据文件不存在 → 跳过OMAV过滤")

    # ── Step 4: 逐股扫描 ──
    log("[STEP3] 开始逐股扫描...")
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
            log("[PROGRESS] %d/%d | candidates=%d B1=%d brick=%d resonance=%d errors=%d" % (
                i, total, len(results), b1_count, brick_count, resonance_count, errors))

        try:
            # 优先用build_prepared_universe缓存的数据
            if code in code_data:
                df = code_data[code]
            else:
                continue  # build_prepared_universe已过滤, 无数据则跳过

            if df is None or len(df) < 160:  # B1 V1最少160bar
                continue

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            # 检查最新日期
            if str(latest.get("trade_date", "")) != TRADE_DATE:
                continue

            close = float(latest.get("close", 0))
            pct_chg = float(latest.get("pct_chg", 0))
            if close <= PRICE_MIN or close > PRICE_MAX:
                continue

            # ── B1 V1信号 ──
            b1_v1 = b1_experimental_v1_ok(df)  # 默认idx=len-1

            # V4-A 前两日结构过滤
            b1_v4a_filtered = False
            if b1_v1 and len(df) >= 3:
                prev1_pct = float(prev.get("pct_chg", 0))
                prev2_pct = float(df.iloc[-3].get("pct_chg", 0))
                if prev1_pct <= V4A_PREV1_MAX and prev2_pct <= V4A_PREV2_MAX:
                    b1_v4a_filtered = True  # V4-A过滤掉
                    log("[V4A-FILTER] %s %s prev1=%.2f%% prev2=%.2f%% → B1被V4-A过滤" % (
                        code, name, prev1_pct, prev2_pct))

            b1_valid = b1_v1 and not b1_v4a_filtered

            # ── 砖型图 V3严格 ──
            brick_raw_turn_red = bool(latest.get("brick_raw_turn_red", False))
            brick_history_ok = bool(latest.get("brick_history_ok", False))
            white = float(latest.get("white_line", 0))
            yellow = float(latest.get("yellow_line", 0))
            high = float(latest.get("high", 0))

            # 条件3: 白线 > 黄线
            white_above_yellow = (white > 0 and yellow > 0 and white > yellow)
            # 条件4: 最高价 >= 白线
            high_above_white = (high >= white * 0.99)  # 允许1%容差

            # 条件5: 板块轮动Top5
            in_rotation_top5 = rotation_map.get((TRADE_DATE, industry), False)

            # 条件6: OMAV — 当前跳过
            omav_ok = True  # 跳过OMAV过滤
            omav_note = "跳过(数据过期)" if not omav_available else "通过"

            # V3严格口径: raw_turn_red + history_ok + 白>黄 + high>=白 + 轮动Top5
            brick_valid = (
                brick_raw_turn_red
                and brick_history_ok
                and white_above_yellow
                and high_above_white
                and in_rotation_top5
                # OMAV暂跳过
            )

            # ── 共振单 ──
            is_resonance = b1_valid and brick_valid

            # ── 无信号则跳过 ──
            if not b1_valid and not brick_valid:
                continue

            if b1_valid:
                b1_count += 1
            if brick_valid:
                brick_count += 1
            if is_resonance:
                resonance_count += 1

            # ── 综合评分 ──
            score = 0.0
            tags = []
            b1_tag = "-"
            brick_tag = "-"

            # B1得分
            if b1_valid:
                score += 3.0
                tags.append("B1(V1+V4-A)")
                b1_tag = "V1+V4-A通过"
                if b1_v4a_filtered:
                    b1_tag += "(V4-A过滤中)"

            # 砖型图得分
            if brick_valid:
                score += 3.0
                tags.append("砖型图V3")
                brick_value = float(latest.get("brick_formula_value", 0))
                brick_tag = "V3通过(砖值=%.1f)" % brick_value

                # A组加分
                brick_a = bool(latest.get("brick_a_group_ok", False))
                if brick_a:
                    score += 1.0
                    brick_tag += "+A组"

                # B组加分
                brick_b = bool(latest.get("brick_b_group_ok", False))
                if brick_b:
                    score += 0.5
                    brick_tag += "+B组"

            # 共振单额外加分
            if is_resonance:
                score += 2.0
                tags.append("共振单")

            # 量价加分
            vol = float(latest.get("vol", 0))
            prev_vol = float(prev.get("vol", 0))
            if prev_vol > 0 and vol > prev_vol * 1.3:
                score += 1.0
                tags.append("放量")
            if pct_chg > 3:
                score += 0.5
                tags.append("强涨(>3%)")

            # 多头排列加分
            if white_above_yellow and close >= white:
                score += 0.5
                tags.append("多头排列")

            # MACD DIF
            dif = float(latest.get("macd_dif", 0))
            if dif > 0:
                score += 0.5

            # 板块加分
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

            # 过滤低分
            if score < MIN_SCORE:
                continue

            # 蜡烛图形态
            candle_pattern = identify_candle(df)

            # 止盈止损参考
            stop_profit = round(close * 1.08, 2)   # +8%
            stop_loss = round(close * 0.96, 2)      # -4%
            yellow_stop = round(yellow, 2)           # 黄线止损位

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
                "stop_profit": stop_profit,
                "stop_loss": stop_loss,
                "yellow_stop": yellow_stop,
                "is_resonance": is_resonance,
                "rotation_top5": in_rotation_top5,
                "omav_note": omav_note,
            })
        except Exception as e:
            errors += 1
            if errors <= 20:
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

    # 排序: 共振单优先 → tier升序(T0先) → score降序
    results.sort(key=lambda x: (0 if x["is_resonance"] else 1, x["tier"], -x["score"]))

    # 统计
    stats = {
        "scan_date": TRADE_DATE,
        "total_scanned": total,
        "candidates": len(results),
        "b1_count": b1_count,
        "brick_count": brick_count,
        "resonance_count": resonance_count,
        "errors": errors,
        "omav_available": omav_available,
        "rotation_top5_count": len(rotation_map),
        "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    return results, stats


if __name__ == "__main__":
    results, stats = scan()

    # 输出JSON到文件
    output = {
        "stats": stats,
        "candidates": results,
    }
    output_file = OUTPUT_DIR / ("scan_%s.json" % TRADE_DATE)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log("[OUTPUT] JSON已写入: %s" % output_file)

    # stdout也输出JSON (方便pipe)
    print(json.dumps(output, ensure_ascii=False, indent=2))
