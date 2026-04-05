def margin_policy_for_industry(industry: str, margin_net_buy_5: float = 0.0, margin_positive_days_5: float = 0.0, margin_rzye_change_5: float = 0.0):
    try:
        net_buy_5 = float(margin_net_buy_5 or 0)
    except Exception:
        net_buy_5 = 0.0
    try:
        positive_5 = float(margin_positive_days_5 or 0)
    except Exception:
        positive_5 = 0.0
    try:
        rzye_change_5 = float(margin_rzye_change_5 or 0)
    except Exception:
        rzye_change_5 = 0.0

    score = 0.0
    reason = []

    if net_buy_5 > 0:
        score += 1.0
        reason.append('近5日融资净买入为正')
    if positive_5 >= 3:
        score += 1.0
        reason.append('近5日融资承接稳定')
    if rzye_change_5 > 0:
        score += 0.5
        reason.append('融资余额抬升')

    if industry == '软件服务' and positive_5 >= 4:
        score += 0.5
        reason.append('软件服务融资延续性较强')
    elif industry == '元器件' and net_buy_5 > 0 and positive_5 >= 3:
        score += 0.5
        reason.append('元器件融资共振')
    elif industry == '电气设备' and rzye_change_5 > 0:
        score += 0.5
        reason.append('电气设备融资余额改善')

    return {
        'margin_score': score,
        'margin_positive': score >= 2.0,
        'margin_reason': '、'.join(reason),
    }
