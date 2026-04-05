from .action_labels import candidate_strategy_tag


def route_tactic(candidate: dict) -> dict:
    strategy_tag = candidate.get('strategy_tag') or candidate_strategy_tag(candidate)
    trend_tier = candidate.get('trend_tier', '') or ''
    execution_style = candidate.get('execution_style', '') or ''
    reason = candidate.get('reason', '') or ''
    confirm_tier = candidate.get('secondary_confirm_tier', '') or ''
    pct_chg = float(candidate.get('pct_chg', 0) or 0)
    week_b1 = bool(candidate.get('week_b1', False))
    day_b1 = bool(candidate.get('day_b1', False))
    perfect_b1 = bool(candidate.get('perfect_b1', False))
    standard_b1 = bool(candidate.get('standard_b1', False))
    weak_b1 = bool(candidate.get('weak_b1', False))

    tactic_family = 'observe'
    tactic_signal = '观察'
    tactic_note = '先观察，不急于归入明确战术。'
    tactic_bucket = 'observe_generic'

    if week_b1 and day_b1:
        tactic_family = 'mainline'
        tactic_signal = '周日B1共振'
        tactic_note = '周B1与日B1同时出现，优先级最高。'
        tactic_bucket = 'mainline_week_day_b1_resonance'
    elif (
        candidate.get('single_pin_low20', False)
        or candidate.get('single_pin_four_zero', False)
        or candidate.get('single_pin_white_cross_red', False)
        or candidate.get('single_pin_white_cross_yellow', False)
        or '单针' in reason
        or '白线下20' in reason
    ):
        tactic_family = 'theme_ultra'
        tactic_signal = '单针下20'
        tactic_note = '偏超短偷袭型，需快速验证成本区脱离。'
        tactic_bucket = 'theme_single_pin_low20'
    elif candidate.get('brick_formula_strong_signal', False) or candidate.get('brick_formula_signal', False) or candidate.get('brick_exec_ready', False) or candidate.get('brick_red_turn', False) or '砖型图' in reason:
        tactic_family = 'daily_exec'
        tactic_signal = '砖型图'
        tactic_note = '偏日级执行战术，注意次日不追高和弱转强确认。'
        tactic_bucket = 'theme_brick_exec'
    elif '埋伏观察' in strategy_tag or '埋伏观察' in execution_style:
        tactic_family = 'observe'
        tactic_signal = '防守轮动埋伏观察'
        tactic_note = '更适合埋伏观察，不适合一致性追高。'
        tactic_bucket = 'defensive_rotation_ambush'
    elif '主线趋势' in strategy_tag and trend_tier == '主线趋势-优先':
        if week_b1 and (perfect_b1 or confirm_tier == 'strong_confirm' or pct_chg >= 4 or candidate.get('b1_strength', 0) >= 5):
            tactic_family = 'mainline'
            tactic_signal = '周B1/主线进攻'
            tactic_note = '周级B1成立且强度较高，偏主线强化进攻阶段。'
            tactic_bucket = 'mainline_week_b1_attack'
        elif week_b1 or perfect_b1 or standard_b1 or candidate.get('b1_strength', 0) >= 4:
            tactic_family = 'mainline'
            tactic_signal = '周B1/主线观察'
            tactic_note = '偏主线战术，优先按周级B1逻辑观察。'
            tactic_bucket = 'mainline_week_b1_observe'
        else:
            tactic_family = 'mainline'
            tactic_signal = '主线修复观察'
            tactic_note = '主线结构未完全走坏，但更偏修复观察而非直接进攻。'
            tactic_bucket = 'mainline_repair_watch'
    elif '主线趋势' in strategy_tag:
        tactic_family = 'mainline'
        tactic_signal = '主线修复观察'
        tactic_note = '主线结构未完全走坏，但更偏修复观察而非直接进攻。'
        tactic_bucket = 'mainline_repair_watch'
    elif candidate.get('b2_signal', False) or candidate.get('b2_shape_ready', False) or '强势加速' in execution_style or pct_chg >= 4:
        tactic_family = 'theme'
        if candidate.get('b2_strength', 0) >= 6 or candidate.get('b2_volume_double', False):
            tactic_signal = 'B2强进攻'
            tactic_note = 'B2 结构更完整，偏强右侧进攻。'
            tactic_bucket = 'theme_b2_attack_strong'
        else:
            tactic_signal = 'B2进攻'
            tactic_note = '偏主题右侧进攻，但需防追高和冲高回落。'
            tactic_bucket = 'theme_b2_attack'
    elif day_b1 or perfect_b1 or standard_b1 or weak_b1 or strategy_tag in ['轮动补涨', '技术备选']:
        tactic_family = 'theme'
        if perfect_b1:
            tactic_signal = '日B1/完美观察'
            tactic_note = '日级B1强度较高，接近完美B1。'
            tactic_bucket = 'theme_day_b1_perfect'
        elif standard_b1:
            tactic_signal = '日B1/标准观察'
            tactic_note = '日级B1成立，属于标准强度。'
            tactic_bucket = 'theme_day_b1_standard'
        elif weak_b1:
            tactic_signal = '日B1/弱观察'
            tactic_note = '日级B1信号较弱，更适合先观察。'
            tactic_bucket = 'theme_day_b1_weak'
        else:
            tactic_signal = '日B1/主题观察'
            tactic_note = '偏主题战术，按日级B1逻辑观察。'
            tactic_bucket = 'theme_day_b1_observe'

    out = dict(candidate)
    out['tactic_family'] = tactic_family
    out['tactic_signal'] = tactic_signal
    out['tactic_note'] = tactic_note
    out['tactic_bucket'] = tactic_bucket
    return out


def route_tactics(candidates):
    return [route_tactic(c) for c in candidates]
