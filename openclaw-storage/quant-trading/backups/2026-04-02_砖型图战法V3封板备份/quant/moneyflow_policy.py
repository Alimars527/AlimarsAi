def moneyflow_policy_for_industry(industry: str):
    if industry == '电气设备':
        return {
            'hard_filter_divergence': True,
            'prefer_positive_days': False,
            'prefer_positive_5': False,
            'note': '电气设备优先过滤上涨资金背离。',
        }
    if industry == '软件服务':
        return {
            'hard_filter_divergence': False,
            'prefer_positive_days': True,
            'prefer_positive_5': False,
            'note': '软件服务更重视近5日承接稳定。',
        }
    if industry == '元器件':
        return {
            'hard_filter_divergence': False,
            'prefer_positive_days': False,
            'prefer_positive_5': False,
            'note': '元器件暂不做统一 moneyflow 硬过滤。',
        }
    return {
        'hard_filter_divergence': False,
        'prefer_positive_days': False,
        'prefer_positive_5': False,
        'note': '默认不启用行业化 moneyflow 规则。',
    }
