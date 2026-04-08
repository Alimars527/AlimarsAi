def holding_action(review):
    total = review.get('total_pnl_pct', 0)
    day = review.get('day_pnl_pct', 0)
    close = review.get('close') or 0
    support = review.get('support') or close
    pressure = review.get('pressure') or close

    if day <= -7:
        return '减仓观察'
    if total <= -8:
        return '接近止损'
    if close <= support * 1.005:
        return '只看承接，不急卖'
    if close >= pressure * 0.98:
        return '持有但不追高'
    if total > 5:
        return '持有，必要时分批止盈'
    return '继续持有观察'


def holding_trigger_plan(review):
    close = review.get('close') or 0
    support = review.get('support') or close
    pressure = review.get('pressure') or close
    if close <= 0:
        return {}
    return {
        'break_support_exit': round(support * 0.99, 2),
        'reclaim_hold': round(max(close, support * 1.01), 2),
        'rebound_reduce': round(pressure * 0.98, 2),
    }


def candidate_strategy_tag(candidate):
    style = candidate.get('execution_style', '')
    industry = candidate.get('industry', '')
    if candidate.get('b1_experimental_v1', False):
        return 'B1实验版V1'
    if industry in ['半导体', '元器件', '消费电子', '电气设备']:
        return '主线趋势'
    if industry in ['白酒', '医药商业', '化学制药']:
        return '轮动补涨'
    if '埋伏' in style:
        return '埋伏观察'
    if '不追' in style:
        return '不建议追'
    return '技术备选'
