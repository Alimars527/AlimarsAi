from .config import load_preferences
from .action_labels import candidate_strategy_tag
from .entry_calibrator import calibrate_entry_zone
from .trend_tier_map import normalize_trend_tier
from .moneyflow_policy import moneyflow_policy_for_industry
from .hkhold_policy import hkhold_policy_for_industry
from .margin_policy import margin_policy_for_industry
from .secondary_confirmation import secondary_confirmation_tier
from .tactic_router import route_tactic


def rank_candidates_for_execution(candidates):
    prefs = load_preferences().get('candidate_filters', {})
    core = set(prefs.get('core_watch_industries', []))
    preference_mode = prefs.get('preference_mode', 'weak_reference')
    resonance_whitelist = {'证券', '银行', '化工原料', '专用机械', '医疗保健'}
    ranked = []

    for c in candidates:
        score = c.get('score', 0)
        industry = c.get('industry', '')
        style = c.get('execution_style', '')
        tag = candidate_strategy_tag(c)
        rank = score

        line_a = bool(c.get('standard_b1', False)) and bool(c.get('brick_v3', False))
        if line_a:
            rank += 5
        if bool(c.get('rotation_support', False)):
            rank += 3
        if c.get('rotation_support_level') == 'strong':
            rank += 2
        if industry in resonance_whitelist:
            rank += 1

        if preference_mode != 'none' and industry in core:
            rank += 0.5
        if tag == '主线趋势':
            rank += 1
        if tag == '轮动补涨':
            rank += 0.5

        trend_style = c.get('trend_style', '')
        trend_tier = normalize_trend_tier(trend_style) if trend_style else None
        if trend_tier == '主线趋势-优先':
            rank += 2
        elif trend_tier == '主线趋势-谨慎':
            rank -= 1

        mf_policy = moneyflow_policy_for_industry(industry)
        mf_flags = []
        if mf_policy.get('hard_filter_divergence') and c.get('mf_divergence'):
            rank -= 3
            mf_flags.append('资金背离')
        if mf_policy.get('prefer_positive_days') and c.get('mf_positive_days_5_ok'):
            rank += 2
            mf_flags.append('承接稳定')
        if mf_policy.get('prefer_positive_5') and c.get('mf_positive_5'):
            rank += 1
            mf_flags.append('近5日净流入')

        hk_view = hkhold_policy_for_industry(
            industry,
            c.get('hkhold_ratio', 0),
            c.get('hkhold_ratio_change', 0),
            c.get('hkhold_positive_5', 0),
        )
        hk_flags = []
        if hk_view.get('hkhold_positive'):
            rank += 2
            hk_flags.append(hk_view.get('hkhold_reason') or '北向正向')
        elif c.get('hkhold_ratio', 0):
            rank += 0.5
            hk_flags.append('北向覆盖')

        margin_view = margin_policy_for_industry(
            industry,
            c.get('margin_net_buy_5', 0),
            c.get('margin_positive_days_5', 0),
            c.get('margin_rzye_change_5', 0),
        )
        confirm_tier = secondary_confirmation_tier(
            hk_view.get('hkhold_positive'),
            margin_view.get('margin_positive'),
            c.get('mf_positive_days_5', 0),
        )
        confirm_flags = []
        if confirm_tier == 'strong_confirm':
            rank += 3
            confirm_flags.append('强确认')
        elif confirm_tier == 'assist_confirm':
            rank += 1
            confirm_flags.append('辅助确认')
        elif confirm_tier == 'front_only':
            rank -= 1
            confirm_flags.append('仅前筛')

        if '不追' in style:
            rank -= 3
        if '强势加速' in style:
            rank -= 1

        item = dict(c)
        item['line_a_core'] = line_a
        item['priority_score'] = rank
        item['strategy_tag'] = tag
        item['trend_tier'] = trend_tier
        item['moneyflow_flags'] = mf_flags
        item['hkhold_flags'] = hk_flags
        item['secondary_confirm_tier'] = confirm_tier
        item['secondary_confirm_flags'] = confirm_flags
        item['entry_plan'] = calibrate_entry_zone(item)
        ranked.append(item)

    ranked.sort(key=lambda x: (x['priority_score'], x.get('pct_chg', 0)), reverse=True)
    return ranked


def split_candidate_buckets(candidates):
    ranked = rank_candidates_for_execution(candidates)
    core_pool = [c for c in ranked if c.get('line_a_core')]
    other_pool = [c for c in ranked if not c.get('line_a_core')]
    focus = core_pool[:4]
    watch = (core_pool[4:] + other_pool)[:5]
    avoid_chase = [c for c in ranked if '不追' in c.get('execution_style', '') or '强势加速' in c.get('execution_style', '')]
    return focus, watch, avoid_chase
