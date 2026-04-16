#!/usr/bin/env python3
"""
仓位评分独立模块（TaskA）

评分维度（满分10分）：
  - RR比（风险回报比）：3分
  - 板块层级（T0/T1/T2）：2分
  - 趋势强度：2分
  - 量能配合：2分
  - 信号类型：1分

仓位映射：
  ≤5 → 不买
  6  → 10%
  7  → 20%
  8  → 30%
  9  → 40%
  10 → 50%

OMAV调整：OMAV > 2%时仓位 ×1.3，单票上限50%
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd
import numpy as np


# ─── 板块层级定义 ───
SECTOR_TIERS: Dict[str, int] = {
    # T0: AI算力/半导体/芯片/AIDC
    "半导体": 0, "芯片": 0, "人工智能": 0, "AI算力": 0, "AIDC": 0,
    "IT设备": 0, "软件服务": 0, "互联网": 0, "通信设备": 0, "元器件": 0,
    # T1: 光伏/储能/新能源
    "光伏": 1, "储能": 1, "新能源": 1, "电气设备": 1, "锂电": 1,
    "新能源车": 1, "特斯拉": 1, "充电桩": 1, "锂电池": 1,
    # T2: 有色/通信/电力
    "有色": 2, "通信": 2, "电力": 2, "有色金属": 2,
    "小金属": 2, "铜": 2, "铝": 2,
}

# T0行业关键词（模糊匹配用）
T0_KEYWORDS = ["半导体", "芯片", "AI", "算力", "AIDC", "IT设备", "软件",
               "互联网", "通信设备", "元器件", "计算机", "电子"]
T1_KEYWORDS = ["光伏", "储能", "新能源", "锂电", "充电", "电池", "特斯拉"]
T2_KEYWORDS = ["有色", "通信", "电力", "小金属", "铜", "铝", "矿"]

# 回避行业
AVOID_KEYWORDS = ["特高压", "商业航空", "房地产"]


@dataclass
class ScoreResult:
    """评分结果"""
    total_score: int           # 总分（整数）
    rr_score: float            # RR比得分（0~3）
    sector_score: float        # 板块层级得分（0~2）
    trend_score: float         # 趋势强度得分（0~2）
    volume_score: float        # 量能得分（0~2）
    signal_score: float        # 信号类型得分（0~1）
    position_pct: float        # 建议仓位百分比（0~50）
    adjusted_position_pct: float  # OMAV调整后仓位百分比
    details: Dict              # 评分明细（用于调试/展示）


def score_rr(close: float, white_line: float, yellow_line: float,
             support: Optional[float] = None) -> tuple:
    """
    RR比评分（0~3分）
    基于买入价到白线/黄线的关系，以及下方支撑距离计算风险回报比。

    计算逻辑：
    - reward = 白线距离（向上空间）
    - risk = 买入价 - 支撑位（止损空间）
    - RR = reward / risk
    """
    details = {}
    if pd.isna(close) or pd.isna(white_line) or pd.isna(yellow_line) or close <= 0:
        return 0.0, {"rr_ratio": 0, "reason": "数据缺失"}

    # 向上空间：到白线的距离
    reward = max(white_line * 1.02 - close, 0)  # 白线+2%作为目标
    # 向下风险：到支撑位的距离
    if support and support > 0:
        risk = max(close - support, close * 0.03)  # 最小风险3%
    else:
        risk = close * 0.03  # 默认3%止损

    rr_ratio = reward / risk if risk > 0 else 0

    if rr_ratio >= 3.0:
        score = 3.0
    elif rr_ratio >= 2.0:
        score = 2.0
    elif rr_ratio >= 1.5:
        score = 1.0
    else:
        score = 0.0

    details = {"rr_ratio": round(rr_ratio, 2), "reward": round(reward, 2),
               "risk": round(risk, 2), "support": support}
    return score, details


def score_sector(industry: str) -> tuple:
    """
    板块层级评分（0~2分）
    T0 = 2分, T1 = 1.5分, T2 = 1分, 其他 = 0.5分, 回避 = 0分
    """
    details = {"industry": industry}

    # 先检查回避
    for kw in AVOID_KEYWORDS:
        if kw in industry:
            details["tier"] = "回避"
            return 0.0, details

    # 模糊匹配
    for kw in T0_KEYWORDS:
        if kw in industry:
            details["tier"] = "T0"
            return 2.0, details

    for kw in T1_KEYWORDS:
        if kw in industry:
            details["tier"] = "T1"
            return 1.5, details

    for kw in T2_KEYWORDS:
        if kw in industry:
            details["tier"] = "T2"
            return 1.0, details

    # 精确匹配
    if industry in SECTOR_TIERS:
        tier = SECTOR_TIERS[industry]
        if tier == 0:
            details["tier"] = "T0"
            return 2.0, details
        elif tier == 1:
            details["tier"] = "T1"
            return 1.5, details
        else:
            details["tier"] = "T2"
            return 1.0, details

    details["tier"] = "其他"
    return 0.5, details


def score_trend(white_line: float, yellow_line: float,
                close: float, ma5: Optional[float] = None,
                ma10: Optional[float] = None, ma20: Optional[float] = None) -> tuple:
    """
    趋势强度评分（0~2分）
    基于白线>黄线、价格在均线上的位置、均线排列
    """
    details = {}

    if pd.isna(white_line) or pd.isna(yellow_line) or pd.isna(close):
        return 0.0, {"reason": "数据缺失"}

    score = 0.0

    # 条件1：白线在黄线上方（0.5分）
    white_above_yellow = white_line > yellow_line
    if white_above_yellow:
        score += 0.5

    # 条件2：收盘价在白线上方（0.5分）
    close_above_white = close >= white_line * 0.995
    if close_above_white:
        score += 0.5

    # 条件3：均线多头排列（0.5分）—— 需要ma数据
    if ma5 and ma10 and ma20 and not any(pd.isna(x) for x in [ma5, ma10, ma20]):
        bullish_alignment = ma5 > ma10 > ma20
        if bullish_alignment:
            score += 0.5

    # 条件4：白黄线间距>2%（趋势清晰度，0.5分）
    spread_pct = abs(white_line - yellow_line) / yellow_line * 100 if yellow_line > 0 else 0
    if white_above_yellow and spread_pct >= 2.0:
        score += 0.5

    details = {
        "white_above_yellow": white_above_yellow,
        "close_above_white": close_above_white,
        "spread_pct": round(spread_pct, 2),
    }
    return score, details


def score_volume(df: pd.DataFrame, idx: int) -> tuple:
    """
    量能配合评分（0~2分）
    基于信号日量能 vs 前期平均量、放量程度
    """
    details = {}

    if idx < 20 or 'vol' not in df.columns:
        return 0.5, {"reason": "数据不足", "fallback": True}

    vol = pd.to_numeric(df['vol'], errors='coerce')
    close = pd.to_numeric(df['close'], errors='coerce')
    open_ = pd.to_numeric(df['open'], errors='coerce')

    today_vol = vol.iloc[idx]
    avg5_vol = vol.iloc[idx-5:idx].mean()
    avg20_vol = vol.iloc[idx-20:idx].mean()

    if pd.isna(today_vol) or pd.isna(avg20_vol) or avg20_vol <= 0:
        return 0.5, {"reason": "量能数据异常", "fallback": True}

    score = 0.0
    vol_ratio = today_vol / avg20_vol

    # 条件1：放量（相对20日均量）（1分）
    if vol_ratio >= 2.0:
        score += 1.0
    elif vol_ratio >= 1.5:
        score += 0.7
    elif vol_ratio >= 1.2:
        score += 0.4

    # 条件2：阳量（收阳线放量加分）（0.5分）
    is_yang = close.iloc[idx] > open_.iloc[idx]
    prev_yang = close.iloc[idx-1] > open_.iloc[idx-1] if idx > 0 else False
    if is_yang and vol_ratio >= 1.3:
        score += 0.5
    elif prev_yang and is_yang:
        score += 0.3

    # 条件3：量能趋势向好（近5日量能递增）（0.5分）
    if idx >= 5:
        vol_5d = vol.iloc[idx-4:idx+1].values
        vol_increasing = all(vol_5d[i] <= vol_5d[i+1] for i in range(len(vol_5d)-1)
                           if not pd.isna(vol_5d[i]) and not pd.isna(vol_5d[i+1]))
        if vol_increasing:
            score += 0.5

    score = min(score, 2.0)

    details = {
        "vol_ratio": round(vol_ratio, 2),
        "is_yang": bool(is_yang),
        "today_vol": round(today_vol, 0),
        "avg20_vol": round(avg20_vol, 0),
    }
    return score, details


def score_signal(brick_signal: bool = False, b1_signal: bool = False,
                 green_streak: int = 0) -> tuple:
    """
    信号类型评分（0~1分）
    砖型图基础信号=0.5，附加条件+0.5
    """
    details = {"brick": brick_signal, "b1": b1_signal, "green_streak": green_streak}
    score = 0.0

    if brick_signal:
        score += 0.5
        # 绿砖连续天数 >= 4（符合V5-T1条件）
        if green_streak >= 4:
            score += 0.3
        # 额外的砖型图结构质量
        if green_streak >= 5:
            score += 0.2

    return min(score, 1.0), details


def calculate_position(score: int, omav_value: Optional[float] = None,
                       max_single_pct: float = 50.0) -> tuple:
    """
    根据得分计算仓位百分比，并应用OMAV调整
    """
    score_to_position = {
        0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0,  # ≤5不买
        6: 10, 7: 20, 8: 30, 9: 40, 10: 50,
    }
    base_pct = score_to_position.get(score, 0)

    adjusted_pct = base_pct
    # OMAV > 2%时乘以1.3
    if omav_value is not None and omav_value > 2.0:
        adjusted_pct = min(base_pct * 1.3, max_single_pct)

    return base_pct, round(adjusted_pct, 1)


def score_candidate(
    code: str,
    name: str,
    industry: str,
    close: float,
    white_line: float,
    yellow_line: float,
    df: Optional[pd.DataFrame] = None,
    idx: Optional[int] = None,
    support: Optional[float] = None,
    ma5: Optional[float] = None,
    ma10: Optional[float] = None,
    ma20: Optional[float] = None,
    brick_signal: bool = False,
    b1_signal: bool = False,
    green_streak: int = 0,
    omav_value: Optional[float] = None,
    max_single_pct: float = 50.0,
) -> ScoreResult:
    """
    对一个候选票进行综合评分。

    参数：
        code: 股票代码
        name: 股票名称
        industry: 所属行业
        close: 信号日收盘价
        white_line: 信号日白线值
        yellow_line: 信号日黄线值
        df: 该股票的完整K线DataFrame（用于量能评分）
        idx: 信号日在df中的行号
        support: 支撑位（近期最低价）
        ma5/ma10/ma20: 均线值（用于趋势评分）
        brick_signal: 是否触发砖型图信号
        b1_signal: 是否触发B1信号
        green_streak: 绿砖连续天数
        omav_value: 当日OMAV值（用于仓位调整）
        max_single_pct: 单票最大仓位百分比

    返回：
        ScoreResult 对象
    """
    # 1. RR比评分
    rr_score, rr_details = score_rr(close, white_line, yellow_line, support)

    # 2. 板块层级评分
    sector_score, sector_details = score_sector(industry)

    # 3. 趋势强度评分
    trend_score, trend_details = score_trend(
        white_line, yellow_line, close, ma5, ma10, ma20
    )

    # 4. 量能评分
    if df is not None and idx is not None:
        volume_score, volume_details = score_volume(df, idx)
    else:
        volume_score, volume_details = 0.5, {"reason": "无df数据", "fallback": True}

    # 5. 信号类型评分
    signal_score, signal_details = score_signal(brick_signal, b1_signal, green_streak)

    # 汇总
    raw_total = rr_score + sector_score + trend_score + volume_score + signal_score
    total_score = int(round(raw_total))
    total_score = max(0, min(10, total_score))

    # 计算仓位
    base_pct, adjusted_pct = calculate_position(total_score, omav_value, max_single_pct)

    return ScoreResult(
        total_score=total_score,
        rr_score=rr_score,
        sector_score=sector_score,
        trend_score=trend_score,
        volume_score=volume_score,
        signal_score=signal_score,
        position_pct=base_pct,
        adjusted_position_pct=adjusted_pct,
        details={
            "code": code,
            "name": name,
            "industry": industry,
            "rr": rr_details,
            "sector": sector_details,
            "trend": trend_details,
            "volume": volume_details,
            "signal": signal_details,
            "raw_total": round(raw_total, 2),
        },
    )


def score_to_str(result: ScoreResult) -> str:
    """将评分结果格式化为可读字符串"""
    lines = [
        f"[{result.details.get('name','')}] {result.total_score}分 → {result.adjusted_position_pct}%仓位",
        f"  RR={result.rr_score}(RR={result.details['rr'].get('rr_ratio','?')})",
        f"  板块={result.sector_score}({result.details['sector'].get('tier','?')})",
        f"  趋势={result.trend_score}",
        f"  量能={result.volume_score}(倍={result.details['volume'].get('vol_ratio','?')})",
        f"  信号={result.signal_score}",
    ]
    return "\n".join(lines)


# ─── 自测 ───
if __name__ == "__main__":
    # 模拟一个T0行业高分票
    r1 = score_candidate(
        code="600487.SH", name="亨通光电", industry="通信设备",
        close=51.0, white_line=52.5, yellow_line=48.0,
        support=49.0, ma5=51.5, ma10=50.8, ma20=49.5,
        brick_signal=True, green_streak=5, omav_value=2.01,
    )
    print("=== 测试1: T0行业高分票 ===")
    print(score_to_str(r1))
    print()

    # 模拟一个普通行业低分票
    r2 = score_candidate(
        code="000001.SZ", name="测试票", industry="纺织",
        close=10.0, white_line=9.8, yellow_line=10.5,
        support=9.5,
        brick_signal=True, green_streak=3, omav_value=-0.5,
    )
    print("=== 测试2: 普通行业低分票 ===")
    print(score_to_str(r2))
    print()

    # 模拟回避行业
    r3 = score_candidate(
        code="000002.SZ", name="回避票", industry="房地产",
        close=15.0, white_line=16.0, yellow_line=14.0,
        brick_signal=True, green_streak=4, omav_value=1.0,
    )
    print("=== 测试3: 回避行业 ===")
    print(score_to_str(r3))
