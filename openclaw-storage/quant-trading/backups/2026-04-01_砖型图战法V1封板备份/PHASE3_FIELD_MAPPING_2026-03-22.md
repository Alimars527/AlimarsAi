# Phase 3 Field Mapping — 2026-03-22

## 系统输出 -> 跟踪记录字段映射

### latest_summary.json / candidates
- `code` -> 标的代码
- `name` -> 标的名称
- `industry` -> 行业
- `priority_score` -> 候选优先级
- `strategy_tag` -> 标签
- `trend_tier` -> 票性层级
- `secondary_confirm_tier` -> 二次确认层级
- `entry_plan.entry_low` -> 建议区间下沿
- `entry_plan.entry_high` -> 建议区间上沿
- `entry_plan.do_not_chase_above` -> 不追价位

### latest_summary.json / market
- `regime` -> 市场环境
- `summary` -> 市场摘要

### latest_summary.json / holdings
- `name` -> 持仓名称
- `status` -> 持仓判断
- `plan` -> 持仓计划
- `support` -> 支撑位
- `pressure` -> 压力位

## Phase 3 每日记录建议新增字段
- 是否执行
- 执行价格
- 执行原因
- 未执行原因
- 次日结果
- 最终退出结果
- 偏差原因
- 系统是否说对
