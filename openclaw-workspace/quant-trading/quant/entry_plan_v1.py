"""买点计划V1 — 三套独立买点体系

B1:  右侧动量反转, 最长10天, 基础[C×0.985, C×0.993], 追高线C×1.010
砖型图: 趋势回踩反转, T+1,   基础[C×0.980, C×0.990], 追高线C×1.005
共振:  双系统共振,   T+1,   基础[C×0.988, C×0.995], 追高线C×1.015

详见 docs/entry_plan_v1.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class EntryPlan:
    """买入计划"""
    strategy_type: str          # B1 / BRICK / RESONANCE
    entry_low: float            # 区间下沿
    entry_high: float           # 区间上沿
    chase_limit: float          # 追高线
    scenario: str               # high_open / flat_open / low_open
    buy_price: Optional[float]  # 最终挂单价 (None=场景不适合)
    hold_days: int              # 持仓天数


def classify_scenario(signal_close: float, next_open: float) -> str:
    if signal_close <= 0:
        return "unknown"
    gap = (next_open / signal_close - 1) * 100
    if gap >= 1.5:
        return "high_open"
    if gap <= -1.5:
        return "low_open"
    return "flat_open"


# ── B1 ──────────────────────────────────────────────
def _b1(
    C: float, pct: float, vol_ratio: float, j: float,
    next_open: float, next_low: float,
) -> EntryPlan:
    # 基础
    low  = C * 0.985
    high = C * 0.993
    chase = C * 1.010

    # 涨幅修正
    if pct >= 5.0:
        low, high = C * 0.980, C * 0.988
    elif pct < 2.0:
        low, high = C * 0.988, C * 0.995

    # 放量修正
    if vol_ratio >= 2.0:
        high += C * 0.005

    # J值修正
    if j <= 0:
        low  += C * 0.005
        high += C * 0.005

    scenario = classify_scenario(C, next_open)
    buy = None

    if scenario == "high_open":
        eff = min(high, chase)
        if next_low <= eff:
            buy = eff
    elif scenario == "low_open":
        low, high = C * 0.978, C * 0.985
        if next_low <= high:
            buy = high
    else:
        if next_low <= high:
            buy = high

    return EntryPlan("B1", low, high, chase, scenario, buy, 10)


# ── 砖型图 ──────────────────────────────────────────
def _brick(
    C: float, pct: float, green_streak: int,
    W: float, Y: float,
    next_open: float, next_low: float,
) -> EntryPlan:
    # 基础
    low  = C * 0.980
    high = C * 0.990
    chase = C * 1.005

    # 绿砖连修正
    if green_streak >= 6:
        low  += C * 0.003
        high += C * 0.003

    # 翻红日涨跌幅
    if pct >= 3.0:
        high += C * 0.005
    elif pct < 0:
        low -= C * 0.005

    # 白黄线间距(趋势强度)
    if W > 0 and Y > 0:
        r = W / Y
        if r > 1.05:
            low += C * 0.003
        elif r < 1.02:
            low, high = C * 0.978, C * 0.985

    scenario = classify_scenario(C, next_open)
    buy = None

    if scenario == "high_open":
        eff = min(high, chase)
        if next_low <= eff:
            buy = eff
    elif scenario == "low_open":
        low, high = C * 0.973, C * 0.985
        if next_low <= high:
            buy = high
    else:
        if next_low <= high:
            buy = high

    return EntryPlan("BRICK", low, high, chase, scenario, buy, 1)


# ── 共振 ────────────────────────────────────────────
def _resonance(
    C: float, pct: float, vol_ratio: float, j: float,
    green_streak: int,
    next_open: float, next_low: float,
) -> EntryPlan:
    # 基础(最宽松)
    low  = C * 0.988
    high = C * 0.995
    chase = C * 1.015

    # 涨幅修正
    if pct >= 5.0:
        low, high = C * 0.983, C * 0.990
    elif pct < 2.0:
        low, high = C * 0.990, C * 0.997

    # 双信号叠加
    if j <= 0 and green_streak >= 6:
        low  += C * 0.005
        high += C * 0.005
    if vol_ratio >= 2.0:
        high += C * 0.005

    scenario = classify_scenario(C, next_open)
    buy = None

    if scenario == "high_open":
        gap = (next_open / C - 1) * 100
        if gap > 3.0:
            eff = min(C * 0.995, chase)
        else:
            eff = min(next_open * 0.998, chase)
        if next_low <= eff:
            buy = eff
    elif scenario == "low_open":
        low, high = C * 0.980, C * 0.988
        if next_low <= high:
            buy = high
    else:
        if next_low <= high:
            buy = high

    return EntryPlan("RESONANCE", low, high, chase, scenario, buy, 1)


# ── 统一入口 ────────────────────────────────────────
def compute_entry_v1(
    is_b1: bool,
    is_brick: bool,
    signal_close: float,
    pct_chg: float,
    vol_ratio: float,
    j_value: float,
    green_streak: int,
    white_line: float,
    yellow_line: float,
    next_open: float,
    next_low: float,
) -> Optional[EntryPlan]:
    """根据信号类型和参数计算 V1 买点"""
    if is_b1 and is_brick:
        return _resonance(
            signal_close, pct_chg, vol_ratio, j_value,
            green_streak, next_open, next_low,
        )
    if is_brick:
        return _brick(
            signal_close, pct_chg, green_streak,
            white_line, yellow_line, next_open, next_low,
        )
    if is_b1:
        return _b1(
            signal_close, pct_chg, vol_ratio, j_value,
            next_open, next_low,
        )
    return None
