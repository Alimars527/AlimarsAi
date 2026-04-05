def hkhold_policy_for_industry(industry: str, hkhold_ratio: float = 0.0, hkhold_ratio_change: float = 0.0, hkhold_positive_5: float = 0.0):
    try:
        ratio = float(hkhold_ratio or 0)
    except Exception:
        ratio = 0.0
    try:
        ratio_change = float(hkhold_ratio_change or 0)
    except Exception:
        ratio_change = 0.0
    try:
        positive_5 = float(hkhold_positive_5 or 0)
    except Exception:
        positive_5 = 0.0

    score = 0.0
    reason = []

    if ratio > 0:
        score += 0.5
        reason.append('北向覆盖')

    if industry == '软件服务':
        if positive_5 >= 2:
            score += 1.0
            reason.append('北向近5日承接较稳')
        if ratio_change > 0:
            score += 0.5
            reason.append('北向增持')
    elif industry == '电气设备':
        if ratio >= 1.0:
            score += 1.0
            reason.append('北向持股比例较高')
        if positive_5 >= 1.5:
            score += 0.5
            reason.append('北向连续性尚可')
    elif industry == '元器件':
        if ratio >= 0.8:
            score += 0.5
            reason.append('北向覆盖较明确')
        if positive_5 >= 1.8:
            score += 0.5
            reason.append('北向承接偏稳')

    return {
        'hkhold_score': score,
        'hkhold_reason': '、'.join(reason),
        'hkhold_positive': score >= 1.0,
    }
