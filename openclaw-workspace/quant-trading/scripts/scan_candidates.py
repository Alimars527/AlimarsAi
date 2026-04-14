#!/usr/bin/env python3
"""全市场候选票扫描 - B1 + 砖型图信号"""
import sys, json, os
sys.path.insert(0, str(os.path.dirname(__file__) + "/.."))

import pandas as pd
from pathlib import Path
from quant.sim_replay_common import (
    load_universe, prepare_code_df, V4_EXCLUDED_INDUSTRIES, DATA
)

TRADE_DATE = "20260414"
START_DATE = "20250101"

# 板块优先级映射
T0 = {"AI算力","半导体","芯片","AIDC","人工智能","IT设备","通信设备","软件服务","互联网"}
T1 = {"光伏","储能","新能源","电气仪表","化工原料","化肥农药"}
T2 = {"有色","通信","电力","矿物制品","新材料"}

def sector_tier(industry: str) -> int:
    if industry in T0: return 0
    if industry in T1: return 1
    if industry in T2: return 2
    return 3

def scan():
    meta = load_universe(DATA, excluded_industries=V4_EXCLUDED_INDUSTRIES)
    print(f"[INFO] Universe size: {len(meta)} (after filters)")

    results = []
    total = len(meta)
    errors = 0

    for i, row in enumerate(meta.itertuples(index=False), 1):
        code = row.ts_code
        name = row.name
        industry = row.industry

        if i % 500 == 0:
            print(f"[PROGRESS] {i}/{total} scanned, {len(results)} candidates so far, {errors} errors")

        try:
            df = prepare_code_df(code, START_DATE, TRADE_DATE, DATA)
            if df is None or len(df) < 30:
                continue

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            # 检查最新日期是否为今日
            if str(latest.get("trade_date", "")) != TRADE_DATE:
                continue

            close = float(latest.get("close", 0))
            pct_chg = float(latest.get("pct_chg", 0))
            if close <= 3 or close > 300:  # 价格过滤
                continue

            # === B1 信号检测 ===
            day_b1 = bool(latest.get("day_b1", False))
            b1_strength = int(latest.get("b1_strength", 0) or 0)
            b1_dif_positive = bool(latest.get("b1_dif_positive", False))
            b1_white_above_yellow = bool(latest.get("b1_white_above_yellow", False))
            b1_volume_expand = bool(latest.get("b1_volume_expand", False))
            b1_price_expand = bool(latest.get("b1_price_expand", False))
            perfect_b1 = bool(latest.get("perfect_b1", False))
            standard_b1 = bool(latest.get("standard_b1", False))

            # B1右侧验证：不在连续下跌中
            b1_right_side = True
            if len(df) >= 5:
                recent_closes = df["close"].iloc[-5:].tolist()
                # 最近5日有4天下跌则视为连续下跌
                down_count = sum(1 for j in range(1, len(recent_closes)) if recent_closes[j] < recent_closes[j-1])
                if down_count >= 4:
                    b1_right_side = False

            b1_valid = day_b1 and b1_right_side

            # === 砖型图信号检测 ===
            brick_formula_signal = bool(latest.get("brick_formula_signal", False))
            brick_formula_strong = bool(latest.get("brick_formula_strong_signal", False))
            brick_formula_turn_red = bool(latest.get("brick_formula_turn_red", False))
            brick_formula_green = bool(latest.get("brick_formula_green", False))
            brick_a_group = bool(latest.get("brick_a_group_ok", False))
            brick_b_group = bool(latest.get("brick_b_group_ok", False))
            brick_history_ok = bool(latest.get("brick_history_ok", False))
            brick_value = float(latest.get("brick_formula_value", 0) or 0)
            prev_brick_value = float(prev.get("brick_formula_value", 0) or 0)

            # 砖型图：绿转红 + 砖值增长 + 历史足够
            brick_valid = brick_formula_turn_red and brick_history_ok and brick_value > prev_brick_value

            # === 信号综合评分 ===
            score = 0
            tags = []
            b1_tag = "❌"
            brick_tag = "❌"

            if b1_valid:
                score += 3
                tags.append("B1信号")
                b1_tag = f"✅ strength={b1_strength}"
                if perfect_b1:
                    score += 1
                    b1_tag += "(完美)"
                if standard_b1:
                    score += 0.5
                    b1_tag += "(标准)"

            if brick_valid:
                score += 3
                tags.append("砖型图")
                brick_tag = "✅ 砖值={:.1f}".format(brick_value)
                if brick_formula_strong:
                    score += 1
                    brick_tag += "(强)"
                if brick_a_group:
                    score += 0.5
                    brick_tag += "(A组)"

            # 量价加分
            vol = float(latest.get("vol", 0))
            prev_vol = float(prev.get("vol", 0))
            if vol > prev_vol * 1.3:
                score += 1
                tags.append("放量")
            if pct_chg > 3:
                score += 0.5
                tags.append("强涨")

            # 白线黄线位置
            white = float(latest.get("white_line", 0))
            yellow = float(latest.get("yellow_line", 0))
            if white > yellow and close > white:
                score += 0.5
                tags.append("多头排列")

            # MACD DIF > 0
            dif = float(latest.get("macd_dif", 0))
            if dif > 0:
                score += 0.5

            # 板块加分
            tier = sector_tier(industry)
            if tier == 0:
                score += 1.5
                tags.append("T0主线")
            elif tier == 1:
                score += 1
                tags.append("T1支线")
            elif tier == 2:
                score += 0.5
                tags.append("T2")

            # 只保留有B1或砖型图信号，且总分>=3的
            if (b1_valid or brick_valid) and score >= 3:
                # 蜡烛图形态识别
                candle_pattern = identify_candle(df)

                results.append({
                    "name": name,
                    "ts_code": code,
                    "industry": industry,
                    "close": close,
                    "pct_chg": round(pct_chg, 2),
                    "score": round(score, 1),
                    "tier": tier,
                    "b1_tag": b1_tag,
                    "brick_tag": brick_tag,
                    "tags": tags,
                    "candle": candle_pattern,
                    "white": round(white, 2),
                    "yellow": round(yellow, 2),
                })
        except Exception as e:
            errors += 1
            continue

    print(f"\n[DONE] Scanned {total} stocks, {len(results)} candidates, {errors} errors")

    # 排序：先按tier升序（T0优先），再按score降序
    results.sort(key=lambda x: (x["tier"], -x["score"]))
    return results


def identify_candle(df: pd.DataFrame) -> str:
    """识别最近几日的蜡烛图形态"""
    if len(df) < 3:
        return "数据不足"

    c = df["close"].iloc[-1]
    o = df["open"].iloc[-1]
    h = df["high"].iloc[-1]
    l = df["low"].iloc[-1]
    prev_c = df["close"].iloc[-2]
    prev_o = df["open"].iloc[-2]

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

    # 看涨吞没：前阴后阳，且阳线实体完全包住阴线实体
    if prev_c < prev_o and c > o and c > prev_o and o < prev_c:
        return "看涨吞没"

    # 看跌吞没
    if prev_c > prev_o and c < o and c < prev_o and o > prev_c:
        return "看跌吞没"

    # 大阳线
    if c > o and body_ratio > 0.7 and pct_day(df) > 3:
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


def pct_day(df):
    try:
        return float(df["pct_chg"].iloc[-1])
    except:
        return 0


if __name__ == "__main__":
    results = scan()
    # 输出JSON
    print(json.dumps(results, ensure_ascii=False, indent=2))
