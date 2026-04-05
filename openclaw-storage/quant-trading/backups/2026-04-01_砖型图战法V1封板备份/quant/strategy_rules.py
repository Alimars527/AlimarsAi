"""第二阶段：策略规则显式化"""


def main_trend_rule(row):
    """主线趋势：基础趋势硬条件 + 行业化 moneyflow + 元器件质量确认。"""
    reason = []
    if row.get('preferred_industry'):
        reason.append('行业弱参考')
    if row.get('trend_up'):
        reason.append('短趋势向上')
    if row.get('close_above_ma10'):
        reason.append('站上MA10')
    if row.get('strong_vs_market'):
        reason.append('强于市场')
    if row.get('volume_up'):
        reason.append('放量')
    if row.get('below_recent_high'):
        reason.append('接近阶段高位')
    if row.get('not_weak_market'):
        reason.append('非弱市')
    if row.get('prefer_flat_open'):
        reason.append('优先平开承接')
    if row.get('mf_positive_5'):
        reason.append('近5日资金净流入')
    if row.get('mf_positive_days_5_ok'):
        reason.append('近5日资金承接稳定')
    if row.get('mf_strength_ok'):
        reason.append('资金强度正常')
    if row.get('mf_divergence'):
        reason.append('上涨资金背离')
    if row.get('bad_components_candidate'):
        reason.append('元器件低质量信号过密')
    if row.get('components_submodel') == '优质趋势元器件':
        reason.append('优质趋势元器件')
    if row.get('components_submodel') == '低质量趋势元器件':
        reason.append('低质量趋势元器件')
    if row.get('hkhold_positive'):
        reason.append(row.get('hkhold_reason') or '北向信号正向')
    else:
        reason.append('北向信号不足')
    if row.get('margin_positive'):
        reason.append(row.get('margin_reason') or '融资信号正向')
    elif row.get('industry') == '元器件':
        reason.append('元器件融资确认不足')

    must_have = [
        row.get('trend_up'),
        row.get('close_above_ma10'),
        row.get('strong_vs_market'),
        row.get('volume_up'),
        row.get('below_recent_high'),
        row.get('not_weak_market'),
        row.get('prefer_flat_open'),
        row.get('hkhold_positive', False),
    ]
    if row.get('mf_policy_hard_filter_divergence'):
        must_have.append(not row.get('mf_divergence'))
    if row.get('mf_policy_prefer_positive_days'):
        must_have.append(row.get('mf_positive_days_5_ok'))
    if row.get('mf_policy_prefer_positive_5'):
        must_have.append(row.get('mf_positive_5'))
    if row.get('industry') == '元器件':
        must_have.append(row.get('margin_positive', False))
    if row.get('bad_components_candidate'):
        must_have.append(False)
    passed = all(must_have)
    return passed, reason


def rotation_catchup_rule(row):
    reason = []
    if row.get('preferred_industry'):
        reason.append('偏好行业')
    if row.get('trend_up'):
        reason.append('短趋势向上')
    if row.get('volume_up'):
        reason.append('放量')
    if row.get('below_recent_high'):
        reason.append('未脱离过远，具补涨空间')
    passed = len(reason) >= 3
    return passed, reason


def ambush_watch_rule(row):
    reason = []
    if row.get('trend_turning'):
        reason.append('趋势拐点')
    if row.get('volume_up'):
        reason.append('放量')
    if row.get('strong_vs_market'):
        reason.append('强于市场')
    passed = len(reason) >= 2
    return passed, reason


RULES = {
    '主线趋势': main_trend_rule,
    '轮动补涨': rotation_catchup_rule,
    '埋伏观察': ambush_watch_rule,
}
