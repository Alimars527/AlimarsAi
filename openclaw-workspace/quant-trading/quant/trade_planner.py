from .report_formatter import classify_candidates
from .action_labels import holding_action, candidate_strategy_tag, holding_trigger_plan
from .priority_ranker import split_candidate_buckets, rank_candidates_for_execution


def _brick_layers(candidates):
    base = [c for c in (candidates or []) if c.get('brick_v3', False)]
    a_group = [c for c in base if c.get('brick_a_group_ok')]
    ab_group = [c for c in a_group if c.get('brick_b_group_ok')]
    abc_group = [c for c in ab_group if c.get('brick_c_group_ok')]
    return base, a_group, ab_group, abc_group


def _strategy_checkbox(v):
    return '☑' if bool(v) else '☐'


def _candidate_trade_levels(candidate):
    ep = candidate.get('entry_plan', {}) or {}
    low = ep.get('entry_low')
    high = ep.get('entry_high')
    chase = ep.get('do_not_chase_above')
    close = float(candidate.get('close', 0) or 0)
    entry_ref = low or high or close or None
    if entry_ref:
        take_profit = round(entry_ref * 1.08, 2)
        stop_loss = round(entry_ref * 0.96, 2)
    else:
        take_profit = None
        stop_loss = None

    if candidate.get('b1_v3', False):
        sell_strategy = '先看 8% 左右止盈；跌破止损位离场，冲高可分批减仓'
    elif candidate.get('b1_experimental_v1', False):
        sell_strategy = '按实验版V1执行：10%减半、20%再减；走弱或破位离场'
    elif candidate.get('brick_v3', False):
        sell_strategy = '按砖型图V3执行：次日/短线不强则走，冲高优先兑现'
    else:
        sell_strategy = '观察票，未到买点不动；买后优先看承接，不强就撤'

    if low and high:
        buy_text = f'{low} ~ {high}'
    else:
        buy_text = '-'

    return {
        'buy_text': buy_text,
        'sell_strategy': sell_strategy,
        'take_profit': take_profit if take_profit is not None else '-',
        'stop_loss': stop_loss if stop_loss is not None else '-',
    }


def _append_strategy_table(lines, candidates):
    ranked = rank_candidates_for_execution(candidates or [])
    lines.append('## 三列候选表（B1_V3 / B1实验版V1 / 砖型图 V3）')
    lines.append('> 说明：B1_V3 这里按最优正式候选口径理解；若当日无命中，则对应列为空勾。')
    lines.append('')
    if not ranked:
        lines.append('- 今日无候选股。')
        lines.append('')
        return
    lines.append('| 推荐序 | 标的 | 代码 | 行业 | B1_V3 | B1实验版V1 | 砖型图 V3 | 建议买入点 | 卖出策略 | 止盈 | 止损 | 备注 |')
    lines.append('|---:|---|---|---|---|---|---|---|---|---:|---:|---|')
    for i, c in enumerate(ranked, start=1):
        note_parts = []
        if c.get('line_a_core'):
            note_parts.append('多策略重合')
        if '资金背离' in str(c.get('reason', '')):
            note_parts.append('有资金背离提示')
        if not note_parts:
            note_parts.append('按候选优先级观察')
        lv = _candidate_trade_levels(c)
        lines.append(
            f"| {i} | {c.get('name','')} | {c.get('code','')} | {c.get('industry','')} | "
            f"{_strategy_checkbox(c.get('b1_v3', False))} | "
            f"{_strategy_checkbox(c.get('b1_experimental_v1', False))} | "
            f"{_strategy_checkbox(c.get('brick_v3', False))} | "
            f"{lv['buy_text']} | {lv['sell_strategy']} | {lv['take_profit']} | {lv['stop_loss']} | {'；'.join(note_parts)} |"
        )
    lines.append('')


def build_trade_plan(holding_reviews, market_summary, sector_rotation, candidates=None, rotation_report=None):
    lines = []
    lines.append('# 次日交易计划')
    lines.append('')
    lines.append(f"- 市场环境：{market_summary.get('regime', 'unknown')}")
    lines.append(f"- 市场摘要：{market_summary.get('summary', '')}")
    lines.append('')
    lines.append('## 板块轮动')
    if rotation_report:
        if rotation_report.get('leaders'):
            lines.append('### 当前主线')
            for item in rotation_report['leaders'][:5]:
                lines.append(f"- {item['industry']}: 当日{item['latest_pct']}% / 近3日{item['recent3_pct']}% / 均值{item['avg_pct']}%")
        if rotation_report.get('ambush'):
            lines.append('### 可埋伏观察')
            for item in rotation_report['ambush'][:5]:
                lines.append(f"- {item['industry']}: 前弱后强，最新{item['latest_pct']}%")
        if rotation_report.get('avoid'):
            lines.append('### 回避方向')
            for item in rotation_report['avoid'][:5]:
                lines.append(f"- {item['industry']}: 最新{item['latest_pct']}%，短线偏弱")
    else:
        for item in sector_rotation[:5]:
            lines.append(f"- {item['industry']}: {item['avg_pct_chg']}% / 胜率{item.get('win_rate', 0)}% / {item.get('label', '观察')}")
    lines.append('')
    lines.append('## 持仓预案')
    for r in holding_reviews:
        if 'error' in r:
            lines.append(f"- {r['name']}：{r['error']}")
            continue
        lines.append(f"### {r['name']}（{r['code']}）")
        lines.append(f"- 收盘：{r['close']}")
        lines.append(f"- 当日盈亏：{r['day_pnl_pct']}%")
        lines.append(f"- 总盈亏：{r['total_pnl_pct']}%")
        lines.append(f"- 支撑：{r['support']} / 压力：{r['pressure']}")
        triggers = holding_trigger_plan(r)
        lines.append(f"- 动作建议：{holding_action(r)}")
        lines.append(f"- 触发条件：跌破 {triggers.get('break_support_exit')} 偏离场；反抽 {triggers.get('rebound_reduce')} 可看减仓；站回 {triggers.get('reclaim_hold')} 可继续拿")
        lines.append(f"- 计划：{r['plan']}")
        scenarios = r.get('scenarios', {})
        if scenarios:
            lines.append('- 高开预案：' + scenarios.get('high_open', ''))
            lines.append('- 平开预案：' + scenarios.get('flat_open', ''))
            lines.append('- 低开预案：' + scenarios.get('low_open', ''))
        lines.append('')
    mainline, ambush, technical = classify_candidates(candidates or [])
    focus, watch, avoid_chase = split_candidate_buckets(candidates or [])
    brick_base, brick_a, brick_ab, brick_abc = _brick_layers(candidates or [])
    lines.append('## 砖型图分层')
    lines.append(f"- 今日砖型图总量：{len(brick_base)}")
    if brick_a:
        lines.append('### 满足叠加层A组')
        lines.append('- ' + '、'.join([c.get('name', c.get('code', '未知标的')) for c in brick_a]))
    if brick_ab:
        lines.append('### 满足叠加层A组+B组')
        lines.append('- ' + '、'.join([c.get('name', c.get('code', '未知标的')) for c in brick_ab]))
    if brick_abc:
        lines.append('### 满足叠加层A组+B组+C组')
        for c in brick_abc:
            extras = []
            if c.get('brick_c2_with_b1'):
                extras.append('B1')
            if c.get('brick_c2_with_b2'):
                extras.append('B2')
            extra_text = f"（叠加{'/'.join(extras)}）" if extras else ''
            lines.append(f"- {c.get('name', c.get('code', '未知标的'))}{extra_text}")
    lines.append('')
    lines.append('## 候选股')
    if not candidates:
        lines.append('- 暂无候选股')
    else:
        lines.append('### 核心推荐（线A优先）')
        if focus:
            for c in focus:
                ep = c.get('entry_plan', {})
                lines.append(f"- {c['name']}（{c['code']} / {c['industry']}）: 优先级{c.get('priority_score')}，标签：{candidate_strategy_tag(c)}，原因：{c['reason']} / 执行属性：{c.get('execution_style','')} / 建议区间：{ep.get('entry_low')}~{ep.get('entry_high')} / {ep.get('do_not_chase_above')}以上不追")
        else:
            lines.append('- 今日核心推荐为空（未出现满足线A核心条件的正式候选）')
        if watch:
            lines.append('### 观察候选（非核心推荐）')
            for c in watch:
                lines.append(f"- {c['name']}（{c['code']} / {c['industry']}）: 优先级{c.get('priority_score')}，标签：{candidate_strategy_tag(c)}，原因：{c['reason']} / 执行属性：{c.get('execution_style','')}")
        if avoid_chase:
            lines.append('### 不建议追')
            for c in avoid_chase:
                lines.append(f"- {c['name']}（{c['code']} / {c['industry']}）: {c.get('execution_style','')}")
    lines.append('')
    _append_strategy_table(lines, candidates or [])
    return '\n'.join(lines)
