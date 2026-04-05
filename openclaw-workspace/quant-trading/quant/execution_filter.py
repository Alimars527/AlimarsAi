def classify_execution_style(candidate):
    pct = candidate.get('pct_chg', 0)
    score = candidate.get('score', 0)
    industry = candidate.get('industry', '')
    reason = candidate.get('reason', '')

    if pct >= 9.5:
        return '情绪过热，次日不追'
    if pct >= 6 and '接近阶段高位' in reason:
        return '强势加速，适合观察分歧后的机会'
    if industry in ['半导体', '元器件', '电气设备', '消费电子', '化学制药', '医药商业', '白酒'] and score >= 5:
        return '主线趋势，可重点观察'
    if score >= 4:
        return '可做埋伏观察'
    return '普通备选'


def filter_for_next_day(candidates):
    result = []
    for c in candidates:
        style = classify_execution_style(c)
        c = dict(c)
        c['execution_style'] = style
        if style == '情绪过热，次日不追':
            continue
        result.append(c)
    return result
