from .report_formatter import classify_candidates, status_text, format_rotation
from .action_labels import holding_action, candidate_strategy_tag, holding_trigger_plan
from .priority_ranker import split_candidate_buckets


def _brick_layers(candidates):
    base = [c for c in (candidates or []) if c.get('brick_raw_turn_red') or c.get('brick_formula_signal')]
    a_group = [c for c in base if c.get('brick_a_group_ok')]
    ab_group = [c for c in a_group if c.get('brick_b_group_ok')]
    abc_group = [c for c in ab_group if c.get('brick_c_group_ok')]
    return base, a_group, ab_group, abc_group


def build_narrative(market_summary, sector_rotation, holding_reviews, candidates, rotation_report=None):
    classify_candidates(candidates or [])
    focus_candidates, watch_candidates, avoid_chase = split_candidate_buckets(candidates or [])
    lines = []
    lines.append('# 日终复盘摘要')
    lines.append('')
    lines.append(f"今天市场环境整体偏 **{market_summary.get('regime', 'unknown')}**。{market_summary.get('summary', '')}")
    lines.append('')

    lines.append('## 板块轮动')
    if rotation_report:
        leaders = rotation_report.get('leaders', [])
        continuation = rotation_report.get('continuation', [])
        ambush_sectors = rotation_report.get('ambush', [])
        avoid = rotation_report.get('avoid', [])
        if leaders:
            lines.append('### 当前主线（原始强度）')
            for x in leaders[:5]:
                lines.append(f"- {x['industry']}：当日 {x['latest_pct']}%，近3日 {x['recent3_pct']}%，均值 {x['avg_pct']}%")
        preferred_leaders = [x for x in leaders if x['industry'] in ['半导体', '元器件', '医药商业', '化学制药', '白酒', '消费电子', '软件服务']]
        if preferred_leaders:
            lines.append('### 实战优先方向')
            for x in preferred_leaders[:5]:
                lines.append(f"- {x['industry']}：更贴合当前交易偏好，优先跟踪")
        if continuation:
            lines.append('### 可能延续')
            for x in continuation[:5]:
                lines.append(f"- {x['industry']}：近3日持续走强，最新 {x['latest_pct']}%")
        if ambush_sectors:
            lines.append('### 可埋伏观察')
            for x in ambush_sectors[:5]:
                lines.append(f"- {x['industry']}：前弱后强，最新 {x['latest_pct']}%")
        if avoid:
            lines.append('### 回避方向')
            for x in avoid[:5]:
                lines.append(f"- {x['industry']}：最新 {x['latest_pct']}%，短线偏弱")
    elif sector_rotation:
        lines.extend(format_rotation(sector_rotation))
    else:
        lines.append('- 今日板块数据暂不充分。')
    lines.append('')

    lines.append('## 持仓复盘结论')
    for r in holding_reviews:
        if 'error' in r:
            lines.append(f"- {r['name']}：数据不足。")
            continue
        triggers = holding_trigger_plan(r)
        lines.append(
            f"- {r['name']}：收盘 {r['close']}，当日 {r['day_pnl_pct']}%，总盈亏 {r['total_pnl_pct']}%。"
            f" 判断：{status_text(r)}；动作建议：{holding_action(r)}；关键区间看 {r['support']} ~ {r['pressure']}；"
            f"跌破 {triggers.get('break_support_exit')} 偏离场，反抽 {triggers.get('rebound_reduce')} 可看减仓。"
        )
    lines.append('')

    lines.append('## 明日关注')
    lines.append('### 核心推荐（线A优先）')
    if focus_candidates:
        for c in focus_candidates:
            ep = c.get('entry_plan', {})
            tier_text = f"，票性 {c.get('trend_tier')}" if c.get('trend_tier') else ''
            mf_text = ''
            if c.get('moneyflow_flags'):
                mf_text = '，资金流 ' + ' / '.join(c.get('moneyflow_flags'))
            hk_text = ''
            if c.get('hkhold_flags'):
                hk_text = '，北向 ' + ' / '.join(c.get('hkhold_flags'))
            confirm_text = ''
            if c.get('secondary_confirm_flags'):
                confirm_text = '，确认层 ' + ' / '.join(c.get('secondary_confirm_flags'))
            elif c.get('secondary_confirm_tier'):
                confirm_text = f"，确认层 {c.get('secondary_confirm_tier')}"
            tactic_text = f"，战术 {c.get('tactic_signal')}" if c.get('tactic_signal') else ''
            lines.append(
                f"- {c.get('name', c.get('code', '未知标的'))}（{c.get('industry', '未知行业')}）："
                f"标签 {c.get('strategy_tag', candidate_strategy_tag(c))}{tier_text}{mf_text}{hk_text}{confirm_text}{tactic_text}，"
                f"优先级 {c.get('priority_score')}，原因：{c.get('reason', '')}。"
                f"建议区间 {ep.get('entry_low')}~{ep.get('entry_high')}，{ep.get('do_not_chase_above')} 以上不追。"
            )
    else:
        lines.append('- 今日核心推荐为空（未出现满足线A核心条件的正式候选）。')
    if watch_candidates:
        lines.append('### 观察候选（非核心推荐）')
        for c in watch_candidates[:5]:
            lines.append(
                f"- {c.get('name', c.get('code', '未知标的'))}（{c.get('industry', '未知行业')}）："
                f"标签 {c.get('strategy_tag', candidate_strategy_tag(c))}，战术 {c.get('tactic_signal', '观察')}，"
                f"执行属性：{c.get('execution_style', '')}。"
            )
    if avoid_chase:
        lines.append('### 不建议追')
        for c in avoid_chase[:3]:
            lines.append(f"- {c.get('name', c.get('code', '未知标的'))}（{c.get('industry', '未知行业')}）：{c.get('execution_style', '')}。")
    if not candidates:
        lines.append('- 当前筛选条件下暂无特别突出的新候选，明天以持仓观察和板块轮动确认优先。')
    lines.append('')
    return '\n'.join(lines)
