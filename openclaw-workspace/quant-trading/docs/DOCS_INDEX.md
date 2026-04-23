# DOCS_INDEX.md

> `quant-trading/docs/` 文档总目录
> 更新日期：2026-04-23

---

## 一、目录说明

### `docs/strategies/`
用于存放：
- 正式策略文档
- 封板版本
- 候选版本草案
- 执行口径与版本总结

优先阅读：
- **`BASELINE_COMBO_STRATEGY_V1_2026-04-23.md`** — **BaseLine组合版策略文档（当前主线）**
  - 回测脚本：`scripts/run_5w_combo_with_tpsl.py`
  - 回测：+219.99% / 585笔 / 50.6%WR / -16.16%DD / CAGR 42.99%
- **`BRICK_STRATEGY_V5_2026-04-16.md`** — V5-T1 纯砖型图冠军（历史参考，+181.50%）
- `BRICK_STRATEGY_V3_2026-04-02.md` — 砖型图 V3 策略（冻结基线）
- `BRICK_EXECUTION_POLICY_V1_2026-04-03.md` — 砖型图执行口径
- `B1_STRATEGY_V2_FINAL_2026-04-03.md` — B1 V2 正式版策略（历史参考）
- `B1_STRATEGY_V3_DRAFT_2026-04-05.md` — B1 V3 草案版（历史参考）
- `STRATEGY_REVIEW_SUMMARY_2026-04-03.md` — 策略总览
- `MULTI_STRATEGY_CAPITAL_ALLOCATION_RULES_2026-04-03.md` — 多策略仓位分配
- `B1_V3_vs_BRICK_V3_COMPARISON_2026-04-05.md` — V3 与砖型图对比
- **`蜡烛图二次确认规则_V1.md`** — 执行层过滤规则（根目录 docs/）

---

### `docs/phase/`
用于存放：
- 项目阶段计划
- 阶段总结
- 每日复盘标准模板
- 回测进度模板

优先阅读：
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
- 数据同步：`DATA_SYNC_NOTE_2026-03-23.md`

---

### `docs/recovery/`
用于存放：
- 历史恢复索引
- 状态快照

注意：根目录的 `RECOVERY_INDEX.md` 是最新版恢复索引，`docs/recovery/` 下的是历史版本。

---

### `reports/战法策略库/`
用于存放：
- 战法版本资料库
- 战法版本总表

优先阅读：
- `reports/战法策略库/战法版本总表.md` — 总入口

---

### `reports/战法回测对比/`
用于存放：
- 回测对比分析报告（主要是B1时代产出，已归档）

---

### `reports/daily/`
每日复盘成品，按日期命名。

---

## 二、推荐恢复顺序
如果上下文丢失，推荐：

1. 先读根目录：`AI_HANDOFF_GUIDE.md`（最全面）
2. 再读根目录：`RECOVERY_INDEX.md`
3. 再读：`STATE_SNAPSHOT.md`（最快恢复上下文）
4. 再读：`docs/strategies/BRICK_STRATEGY_V5_2026-04-16.md`（纯砖型图历史参考）
5. 再读本文件：`docs/DOCS_INDEX.md`
6. 再读：`outputs/OUTPUTS_INDEX.md`
7. 最后按需要进入 `reports/daily/` 看最新日报

---

## 三、当前最重要的几份文档

### 项目入口文件
- `AI_HANDOFF_GUIDE.md` — AI 接手总指南
- `RECOVERY_INDEX.md` — 恢复索引
- `STATE_SNAPSHOT.md` — 状态快照（最快恢复）
- `README.md` — 项目说明

### 当前主线策略（BaseLine组合版）
- `docs/strategies/BASELINE_COMBO_STRATEGY_V1_2026-04-23.md` — **正式策略文档**
- 根目录 `AI_HANDOFF_GUIDE.md` §3.1 — 项目级综合描述
- Hermes skill：`baseline-strategy-reference` — 速查参考
- 回测脚本：`scripts/run_5w_combo_with_tpsl.py`

### 纯砖型图历史参考（V5-T1）
- `docs/strategies/BRICK_STRATEGY_V5_2026-04-16.md`

### 执行层规则
- `docs/蜡烛图二次确认规则_V1.md` — 候选票买入前二次确认

### 最新日报
- `reports/daily/`

### 输出索引
- `outputs/OUTPUTS_INDEX.md`

---

## 四、文档更新规则

1. 每次重大阶段推进后，必须更新 `AI_HANDOFF_GUIDE.md` 和 `RECOVERY_INDEX.md`
2. 每次产出新的回测结果，必须更新 `outputs/OUTPUTS_INDEX.md`
3. 每次新增文档，必须更新本文件（`DOCS_INDEX.md`）
4. `@reset` 指令触发时，必须先更新所有引导文件再执行重连
