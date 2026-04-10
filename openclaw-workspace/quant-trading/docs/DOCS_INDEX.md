# DOCS_INDEX.md

> `quant-trading/docs/` 文档总目录
> 更新日期：2026-04-05

## 一、目录说明

### `docs/strategies/`
用于存放：
- 正式策略文档
- 封板版本
- 候选版本草案
- 执行口径与版本总结

优先阅读：
- `docs/strategies/B1_STRATEGY_V2_FINAL_2026-04-03.md`
- `docs/strategies/BRICK_STRATEGY_V3_2026-04-02.md`
- `docs/strategies/B1_STRATEGY_V3_DRAFT_2026-04-05.md`
- `docs/strategies/STRATEGY_REVIEW_SUMMARY_2026-04-03.md`

---

### `docs/phase/`
用于存放：
- 项目阶段计划
- 阶段总结
- Phase 2 / Phase 3 文档
- 历史项目状态文档
- 每日复盘标准模板

优先阅读：
- `docs/phase/PROJECT_STATE_BACKUP_2026-03-18.md`
- `docs/phase/PHASE2_COMPLETION_RECORD_2026-03-22.md`
- `docs/phase/PHASE2_FINALIZATION_SUMMARY_2026-03-22.md`
- `docs/phase/PHASE3_ENTRY_PLAN_2026-03-22.md`
- `docs/phase/DAILY_REVIEW_TEMPLATE_V2_2026-04-05.md`
- `docs/phase/DAILY_REVIEW_OUTPUT_FORMAT_V1_2026-04-05.md`

---

### `docs/research/`
用于存放：
- 研究计划
- 验证笔记
- 专题分析
- 方法论推演与补充说明

典型内容：
- 砖型图修正说明
- Tactic / Bucket / Ultra-short 相关计划
- 结构/行业/输出方案笔记

---

### `docs/recovery/`
用于存放：
- 历史恢复索引
- 状态快照
- 旧恢复入口材料

优先阅读：
- `docs/recovery/RECOVERY_INDEX_2026-03-21.md`
- `docs/recovery/STATE_SNAPSHOT.json`

---

### `reports/战法策略库/`
用于存放：
- 战法版本资料库
- B1正式版各版本
- 砖型图各版本
- B1实验版各版本
- 战法版本总表

优先阅读：
- `reports/战法策略库/战法版本总表.md`
- `reports/战法策略库/B1正式版/`
- `reports/战法策略库/砖型图/`
- `reports/战法策略库/B1实验版/`

---

## 二、推荐恢复顺序
如果上下文丢失，推荐：

1. 先读根目录：`RECOVERY_INDEX.md`
2. 再读：`docs/strategies/B1_STRATEGY_V3_DRAFT_2026-04-05.md`
3. 再读：`docs/strategies/B1_STRATEGY_V2_FINAL_2026-04-03.md`
4. 再读：`docs/strategies/BRICK_STRATEGY_V3_2026-04-02.md`
5. 再看：`outputs/OUTPUTS_INDEX.md`
6. 最后按需要进入 `outputs/` 查证据

---

## 三、当前最重要的几份文档

### 项目当前入口
- `RECOVERY_INDEX.md`
- `README.md`

### 战法当前主线
- `docs/strategies/B1_STRATEGY_V2_FINAL_2026-04-03.md`
- `docs/strategies/BRICK_STRATEGY_V3_2026-04-02.md`
- `docs/strategies/B1_STRATEGY_V3_DRAFT_2026-04-05.md`
- `reports/战法回测对比/B1_V3_位置质量过滤正式版候选_2026-04-07.md`
- `reports/战法回测对比/B1本体优化首轮对照_2026-04-10.md`
- `reports/战法策略库/战法版本总表.md`
- `reports/战法策略库/B1实验版/B1实验版_V4_A_前两日结构过滤版.md`
- `reports/战法策略库/B1实验版/B1实验版_V4_B_前两日结构过滤加avg5轻降权版.md`

### 输出整理入口
- `outputs/OUTPUTS_INDEX.md`

---

## 四、维护原则
- 新的正式策略文档 → 放 `docs/strategies/`
- 新的阶段计划/总结 → 放 `docs/phase/`
- 新的研究笔记/验证笔记 → 放 `docs/research/`
- 历史恢复材料/状态快照 → 放 `docs/recovery/`
- 根目录尽量只保留项目入口文件
- 用户手动提供的环境数值类输入 → 放 `data/manual_inputs/`，并在 README / RECOVERY_INDEX 中同步说明
