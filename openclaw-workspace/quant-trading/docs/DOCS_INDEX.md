# DOCS_INDEX.md

> `quant-trading/docs/` 文档总目录
> 更新日期：2026-04-14

---

## 一、目录说明

### `docs/strategies/`
用于存放：
- 正式策略文档
- 封板版本
- 候选版本草案
- 执行口径与版本总结

优先阅读：
- `B1_STRATEGY_V2_FINAL_2026-04-03.md` — B1 V2 正式版策略
- `B1_STRATEGY_V3_DRAFT_2026-04-05.md` — B1 V3 草案版
- `B1_LAYERED_STRATEGY_2026-04-03.md` — B1 分层策略
- `BRICK_STRATEGY_V3_2026-04-02.md` — 砖型图 V3 策略
- `BRICK_EXECUTION_POLICY_V1_2026-04-03.md` — 砖型图执行口径
- `STRATEGY_REVIEW_SUMMARY_2026-04-03.md` — 策略总览
- `MULTI_STRATEGY_CAPITAL_ALLOCATION_RULES_2026-04-03.md` — 多策略仓位分配
- `B1_V3_vs_BRICK_V3_COMPARISON_2026-04-05.md` — V3 与砖型图对比

---

### `docs/phase/`
用于存放：
- 项目阶段计划
- 阶段总结
- Phase 2 / Phase 3 文档
- 历史项目状态文档
- 每日复盘标准模板
- 回测进度模板

优先阅读：
- `PROJECT_STATE_BACKUP_2026-03-18.md` — 项目初始状态备份
- `PHASE2_COMPLETION_RECORD_2026-03-22.md` — Phase 2 完成记录
- `PHASE3_ENTRY_PLAN_2026-03-22.md` — Phase 3 入口计划
- `DAILY_REVIEW_TEMPLATE_V2_2026-04-05.md` — 复盘模板
- `DAILY_REVIEW_OUTPUT_FORMAT_V1_2026-04-05.md` — 复盘输出格式
- `BACKTEST_PROGRESS_TEMPLATE_V1_2026-04-10.md` — 回测进度模板

---

### `docs/research/`
用于存放：
- 研究计划
- 验证笔记
- 专题分析
- 方法论推演与补充说明

典型内容：
- 砖型图修正说明：`BRICK_FORMULA_FIX_NOTE_2026-03-24.md`
- 砖型图精炼计划：`BRICK_REFINEMENT_PLAN_2026-03-23.md`
- V2 缺口分析：`BRICK_V2_GAP_ANALYSIS_2026-03-30.md`
- Tactic/Bucket/超短执行相关：`NEXT_TACTIC_BUCKETS_PLAN_*`, `ULTRA_SHORT_EXECUTION_*`
- 数据同步：`DATA_SYNC_NOTE_2026-03-23.md`
- 聚焦主题：`FOCUS_THEMES_2026-03-23.md`

---

### `docs/recovery/`
用于存放：
- 历史恢复索引
- 状态快照
- 旧恢复入口材料

优先阅读：
- `RECOVERY_INDEX_2026-03-21.md`

注意：根目录的 `RECOVERY_INDEX.md` 是最新版恢复索引，`docs/recovery/` 下的是历史版本。

---

### `reports/战法策略库/`
用于存放：
- 战法版本资料库
- B1正式版各版本
- 砖型图各版本
- B1实验版各版本
- 战法版本总表

优先阅读：
- `reports/战法策略库/战法版本总表.md` — 总入口
- `reports/战法策略库/B1正式版/`
- `reports/战法策略库/砖型图/`
- `reports/战法策略库/B1实验版/`

---

### `reports/战法回测对比/`
用于存放：
- 回测对比分析报告
- 升格决策面板
- 副作用审计报告
- 口径纯化结论
- 阶段总结

优先阅读（2026-04-12 集中产出）：
- `V4A到190_plus标准桥接结论_2026-04-12.md` — 核心桥接结论
- `V4A_avg5_50标准桥接升格决策面板_2026-04-12.md` — 升格决策
- `V4A_avg5_50副作用审计_2026-04-12.md` — 副作用审计
- `V4A_avg5_50下一步小修正决策_2026-04-12.md` — 窄修正方向
- `稳健线口径纯化结论_2026-04-12.md` — 稳健线重评
- `稳健线重评级与下一轮主线推进建议_2026-04-12.md` — 推进建议

---

## 二、推荐恢复顺序
如果上下文丢失，推荐：

1. 先读根目录：`AI_HANDOFF_GUIDE.md`（最全面）
2. 再读根目录：`RECOVERY_INDEX.md`
3. 再读：`reports/战法策略库/战法版本总表.md`
4. 再读：`reports/战法回测对比/V4A到190_plus标准桥接结论_2026-04-12.md`
5. 再读：`reports/战法回测对比/V4A_avg5_50副作用审计_2026-04-12.md`
6. 再读本文件：`docs/DOCS_INDEX.md`
7. 再读：`outputs/OUTPUTS_INDEX.md`
8. 最后按需要进入 `outputs/` 查证据

---

## 三、当前最重要的几份文档

### 项目入口文件
- `AI_HANDOFF_GUIDE.md` — AI 接手总指南
- `RECOVERY_INDEX.md` — 恢复索引
- `README.md` — 项目说明

### 战法策略总入口
- `reports/战法策略库/战法版本总表.md`

### 当前最新阶段结论
- `reports/战法回测对比/V4A到190_plus标准桥接结论_2026-04-12.md`
- `reports/战法回测对比/V4A_avg5_50标准桥接升格决策面板_2026-04-12.md`
- `reports/战法回测对比/V4A_avg5_50副作用审计_2026-04-12.md`
- `reports/战法回测对比/V4A_avg5_50下一步小修正决策_2026-04-12.md`
- `reports/战法回测对比/稳健线口径纯化结论_2026-04-12.md`
- `reports/战法回测对比/稳健线重评级与下一轮主线推进建议_2026-04-12.md`

### 最新日报
- `outputs/latest_plan.md`
- `reports/daily/`

### 输出索引
- `outputs/OUTPUTS_INDEX.md`

---

## 四、文档更新规则

1. 每次重大阶段推进后，必须更新 `AI_HANDOFF_GUIDE.md` 和 `RECOVERY_INDEX.md`
2. 每次产出新的回测对比报告，必须更新本文件（`DOCS_INDEX.md`）
3. 每次新增 outputs 文件，必须更新 `outputs/OUTPUTS_INDEX.md`
4. 每次改版战法，必须更新 `reports/战法策略库/战法版本总表.md`
