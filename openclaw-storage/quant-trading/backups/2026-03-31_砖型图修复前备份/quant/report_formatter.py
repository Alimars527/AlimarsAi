def classify_candidates(candidates):
    mainline = []
    ambush = []
    technical = []
    for c in candidates:
        if not c.get('name') and not c.get('code'):
            continue
        reason = c.get('reason', '')
        industry = c.get('industry', '')
        style = c.get('execution_style', '')
        if any(k in reason for k in ['偏好行业', '短趋势向上']) and industry in ['半导体', '元器件', '电气设备', '消费电子', '软件服务', '化学制药', '医药商业', '白酒']:
            mainline.append(c)
        elif '埋伏' in style or c.get('score', 0) >= 4:
            ambush.append(c)
        else:
            technical.append(c)
    return mainline, ambush, technical


def status_text(review):
    total = review.get('total_pnl_pct', 0)
    day = review.get('day_pnl_pct', 0)
    close = review.get('close')
    support = review.get('support')
    pressure = review.get('pressure')
    if close is None:
        return '数据不足'
    if day <= -7:
        return '短线承压，优先看是否止跌，必要时减仓观察'
    if close <= (support or close) * 1.01:
        return '接近支撑，先看承接，不急着杀跌'
    if close >= (pressure or close) * 0.98:
        return '接近压力，不追高，等放量确认'
    if total > 5:
        return '已有利润垫，可继续持有并提高警惕'
    if total < -8:
        return '已明显偏弱，重点看止损纪律'
    return '结构未坏，继续观察为主'


def format_rotation(rotation):
    lines = []
    for item in rotation[:5]:
        lines.append(f"- {item['industry']}：均涨 {item['avg_pct_chg']}%，胜率 {item.get('win_rate', 0)}%，状态 {item.get('label', '观察')}")
    return lines
