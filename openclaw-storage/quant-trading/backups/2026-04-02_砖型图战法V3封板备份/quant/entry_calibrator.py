def calibrate_entry_zone(candidate, latest_bar=None):
    """
    根据候选票类型，给出更符合隔日交易现实的建议买入区间。
    candidate: 包含 close/pct_chg/strategy_tag/execution_style 等字段
    latest_bar: 可选，包含 open/high/low/close
    """
    close = float(candidate.get('close', 0) or 0)
    pct = float(candidate.get('pct_chg', 0) or 0)
    tag = candidate.get('strategy_tag', '')
    style = candidate.get('execution_style', '')

    if close <= 0:
        return {
            'entry_low': None,
            'entry_high': None,
            'do_not_chase_above': None,
            'note': '数据不足'
        }

    # 分策略建模：不同票性，不同区间
    if tag == '主线趋势':
        entry_low = round(close * 0.983, 2)
        entry_high = round(close * 0.988, 2)
        do_not_chase = round(close * 1.01, 2)
        note = '主线趋势票：只看平开/小低开回踩，下沿优先，区间上沿仅作为最后观察位。'
    elif tag == '轮动补涨':
        entry_low = round(close * 0.975, 2)
        entry_high = round(close * 0.983, 2)
        do_not_chase = round(close * 1.006, 2)
        note = '轮动补涨票：需要更深一点的低吸，避免区间中上沿成交。'
    elif tag == '埋伏观察':
        entry_low = round(close * 0.965, 2)
        entry_high = round(close * 0.975, 2)
        do_not_chase = round(close * 1.003, 2)
        note = '埋伏观察票：只看更低的位置，不触发就放弃，不接受追价。'
    elif '强势加速' in style:
        entry_low = round(close * 0.962, 2)
        entry_high = round(close * 0.972, 2)
        do_not_chase = round(close * 1.002, 2)
        note = '强势加速票：原则上不追，只看更深的分歧回踩，下沿优先。'
    else:
        entry_low = round(close * 0.972, 2)
        entry_high = round(close * 0.982, 2)
        do_not_chase = round(close * 1.006, 2)
        note = '普通观察票：以区间下沿承接为主，中上沿只观察。'

    # 若当天已明显放量大涨，进一步收紧追高阈值
    if pct >= 5:
        do_not_chase = round(min(do_not_chase, close * 1.005), 2)
        note += ' 当日涨幅较大，次日更不宜追高。'

    return {
        'entry_low': entry_low,
        'entry_high': entry_high,
        'do_not_chase_above': do_not_chase,
        'note': note,
    }
