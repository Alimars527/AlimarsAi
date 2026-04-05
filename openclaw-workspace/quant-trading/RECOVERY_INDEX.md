# RECOVERY_INDEX.md

> 用于上下文丢失、换模型、会话中断后的快速恢复。
> 最后更新：2026-04-05

## 一、当前项目状态（最新口径）

### 当前正式版本
- **B1 战法正式封板版**：`docs/strategies/B1_STRATEGY_V2_FINAL_2026-04-03.md`
- **砖型图正式封板版**：`docs/strategies/BRICK_STRATEGY_V3_2026-04-02.md`

### 当前最新候选版本
- **B1 战法 V3 草案**：`docs/strategies/B1_STRATEGY_V3_DRAFT_2026-04-05.md`
- 当前理解：V3 已完成条件拆解与第二轮精简复核，已形成新候选版本，且已进入每日候选链试运行。

### 当前总览文档
- **统一战法口径汇总**：`docs/strategies/STRATEGY_REVIEW_SUMMARY_2026-04-03.md`

---

## 二、当前关键结论

### 1）B1 战法
- B1 V2 是 2026-04-03 封板版。
- 执行口径：
  - 买点：`min(信号日收盘价 × 0.993, 次日开盘价 × 0.988)`
  - 卖点：固定持有 3 天
- B1 的主问题曾判断为：**信号本体不是核心问题，执行层更关键**。

### 2）B1 战法 V3（最新候选）
- 来源：Task B 条件拆解 + 第二轮精简复核。
- 当前 V3 核心口径：
  - 保留基础硬条件
  - **删除**：`回调幅度 <= 15%`
  - **保留**：`回调时间 <= 15天`
  - **保留**：`量能收束方式B`
  - **保留**：`K线不完全在白线下`
- 当前最优候选版本：`B1_BASE_NEW_PLUS_DAYS_VOLUME`

### 3）砖型图
- 砖型图当前正式版本：**V3**
- 定义：**优质砖型图 V1 + OMAV 硬过滤 + 板块轮动 Top5**
- 当前不直接覆盖 V3；如继续升级，按 V4/V5 递进。

### 4）数据完整性
- 已确认 300308.SZ 的 KDJ/J 不一致问题主要来自**最近交易日数据缺失**，不是公式错误。
- 针对 `20260331` 与 `20260401` 的缺失数据补丁任务已完成。

### 5）模拟盘回放
- 已完成从 `2023-01-01` 到 `2026-04-03` 的 10w 模拟盘回放及多个变体对比。

---

## 三、关键结果文件（优先读）

### B1 Task B
- `outputs/b1_taskB_condition_decompose_summary.json`
- `outputs/b1_taskB_round2_refine_summary.json`

### 砖型图 V3 收束验证
- `outputs/brick_v3_convergence_taskA_summary.json`

### 数据修补
- `outputs/patch_20260331_20260401_missing_progress.json`

### 模拟盘回放
- `outputs/sim_replay_20230101_summary.json`
- `outputs/sim_replay_20230101_planB_summary.json`
- `outputs/sim_replay_20230101_drawdown_guard_summary.json`
- `outputs/sim_replay_20230101_position_tiered_summary.json`

### 每日候选链
- `outputs/daily_review_candidates_20260403.md`
- `outputs/daily_review_candidates_20260403.csv`
- `outputs/daily_review_candidates_20260403.json`

---

## 四、目前可确认的进度判断

### 已完成
- B1 V2 封板
- 砖型图 V3 封板
- 最近缺失交易日数据修补
- B1 Task B 第一轮条件拆解
- B1 Task B 第二轮精简复核
- B1 V3 草案文档落地
- B1 V3 进入每日候选链试运行
- 模拟盘回放主版本与多个风控/仓位版本结果生成

### 待确认 / 待决定
- B1 V3 是否正式封板
- B1 V3 是否彻底替换旧 B1 V2 成为正式日复盘主版本
- 是否补写更系统的 `CHANGELOG.md`

---

## 五、关键备份位置

### 最新关键进展补备份
- `backups/2026-04-05_关键进展补备份/`

该目录已补备份以下内容：
- B1 V2 封板文档
- 砖型图 V3 封板文档
- B1 V3 草案
- 战法总览汇总
- Task B / Task A 关键 summary 输出
- 数据修补进度文件
- 模拟盘回放 summary 文件
- 20260403 每日候选文件

---

## 六、上下文丢失后的推荐恢复顺序
1. 先读本文件：`RECOVERY_INDEX.md`
2. 再读：`docs/strategies/B1_STRATEGY_V3_DRAFT_2026-04-05.md`
3. 再读：`docs/strategies/B1_STRATEGY_V2_FINAL_2026-04-03.md`
4. 再读：`docs/strategies/BRICK_STRATEGY_V3_2026-04-02.md`
5. 如需看证据，再读对应 `outputs/*summary.json`
6. 如需看当天候选，再读 `outputs/daily_review_candidates_20260403.*`

---

## 七、一句话恢复口径
当前项目已从“B1 V2 / Brick V3 定版”推进到“B1 V3 新候选成型并试运行”的阶段；数据缺失问题已做关键修补，模拟盘回放结果也已产出，下一步核心是确认 **B1 V3 是否正式封板并成为新的主版本**。
