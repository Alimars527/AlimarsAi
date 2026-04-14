# OUTPUTS_INDEX.md

> `quant-trading/outputs/` 输出文件总索引
> 更新日期：2026-04-14

## 一、最新产出（2026-04-12 ~ 04-13）

### 核心回测结果
| 文件 | 说明 |
|---|---|
| `sim_replay_...v4a_plus_avg5_band_1_2_deweight_05_v1_summary.json` | **V4-A + avg5 50% 标准桥接（192.77%）** |
| `sim_replay_...v4a_plus_avg5_band_1_2_deweight_05_v1_trades.csv` | 标准桥接交易明细 |
| `sim_replay_...v4a_plus_avg5_band_1_2_deweight_05_v1_nav.csv` | 标准桥接净值曲线 |
| `sim_replay_...narrowfix_v1_summary.json` | 窄修正尝试 v1 |
| `sim_replay_...v4a_plus_avg5_band_1_2_deweight_085_v1_summary.json` | avg5 85% 降权对照（160.35%，已否决） |
| `sim_replay_...v4a_plus_rr_filter_v1_summary.json` | V4-A + RR 过滤 |
| `sim_replay_...v4a_plus_industry_structure_v1_summary.json` | V4-A + 行业结构过滤 |
| `sim_replay_...b1_v3_position_quality_formal_candidate_summary.json` | B1_V3 口径纯化修复后（48.02%） |

### 砖型图桥接实验
| 文件 | 说明 |
|---|---|
| `sim_replay_...strict_brick_v3_dynamic_exit_bridge_summary.json` | 砖型图动态退出桥接 |
| `sim_replay_...strict_brick_v3_keep_rotation_remove_omav_bridge_summary.json` | 砖型图去 OMAV 桥接 |

### 每日复盘
| 文件 | 说明 |
|---|---|
| `latest_plan.md` | 最新复盘报告（2026-04-13） |
| `latest_summary.json` | 最新复盘摘要 JSON |
| `daily_review_candidates_20260410.md/.csv/.json` | 0410 候选链 |

---

## 二、B1 本体优化系列

### V4-A 前两日结构过滤（主线）
| 文件 | 说明 |
|---|---|
| `sim_replay_...b1_prev2_structure_filter_v2a_summary.json` | V4-A v2a 本体（基准） |

### avg5 降权变体
| 文件 | 说明 |
|---|---|
| `sim_replay_...v4a_plus_avg5_band_1_2_deweight_05_*` | 50% 降权（当前最优） |
| `sim_replay_...v4a_plus_avg5_band_1_2_deweight_07_*` | 70% 降权 |
| `sim_replay_...v4a_plus_avg5_band_1_2_deweight_085_*` | 85% 降权 |
| `sim_replay_...v4a_plus_avg5_band_15_2_deweight_*` | (1.5,2] 区间变体 |

### B1 实验版历史
| 文件 | 说明 |
|---|---|
| `sim_replay_...b1_experimental_v1_summary.json` | B1 实验版 V1（153.80%） |
| `sim_replay_...b1_experimental_v2_summary.json` | B1 实验版 V2（83.43%，已否决） |
| `sim_replay_...b1_experimental_v3_avg5_deweight_summary.json` | V3-A avg5 降权 |

### B1 早期实验
| 文件 | 说明 |
|---|---|
| `sim_replay_...b1_space_filter_*` | 空间过滤系列 |
| `sim_replay_...b1_rr_filter_*` | RR 过滤系列 |
| `sim_replay_...b1_forward_rotation_*` | 前向轮动 |
| `sim_replay_...b1_v3_dynamic_exit_*` | V3 动态退出 |
| `sim_replay_...b1_warn_*` | 警告降权系列 |

---

## 三、砖型图系列

| 文件 | 说明 |
|---|---|
| `sim_replay_...strict_brick_v3_only_summary.json` | 砖型图 V3 单独（101.64%） |
| `sim_replay_...brick_bear_deweight_v1_summary.json` | 熊市降权 |
| `sim_replay_...brick_bear_strength_v1_summary.json` | 熊市强度 |
| `sim_replay_...rebound_today_filter_v1_summary.json` | 反弹过滤 |
| `sim_replay_...close_above_white_filter_v1_summary.json` | 收盘白线上过滤 |

---

## 四、组合策略回测

| 文件 | 说明 |
|---|---|
| `sim_replay_20230101_summary.json` | 主版本 |
| `sim_replay_20230101_planB_summary.json` | Plan B |
| `sim_replay_20230101_drawdown_guard_summary.json` | 回撤保护版 |
| `sim_replay_20230101_position_tiered_summary.json` | 分仓版 |

---

## 五、任务/诊断产出

### B1 Task B
| 文件 | 说明 |
|---|---|
| `b1_taskB_condition_decompose_summary.json` | 条件拆解总结 |
| `b1_taskB_round2_refine_summary.json` | 第二轮精简 |

### 砖型图收敛
| 文件 | 说明 |
|---|---|
| `brick_v3_convergence_taskA_summary.json` | 收敛验证 |

### 数据修补
| 文件 | 说明 |
|---|---|
| `patch_*_progress.json` | 各日数据修补进度 |

### 行业/因子诊断
| 文件 | 说明 |
|---|---|
| `industry_diagnostic_latest.json` | 行业诊断 |
| `all_industries_backtest_latest.json` | 全行业回测 |
| `trend_priority_*` | 趋势优先回测 |
| `b1_resonance_*` | 共振实验 |
| `standard_b1_*` | 标准 B1 因子实验 |

---

## 六、子目录

| 目录 | 说明 |
|---|---|
| `backtests/` | 历史回测归档 |
| `diagnostics/` | 诊断工具输出 |
| `reference/` | 参考数据 |
| `repairs/` | 数据修复记录 |
| `reviews/` | 审阅材料 |
| `simulations/` | 模拟盘详情 |
| `task_runs/` | 任务运行记录 |

---

## 七、模拟盘实时文件

| 文件 | 说明 |
|---|---|
| `sim_account.json` | 模拟账户状态 |
| `sim_daily_log.csv` | 每日日志 |
| `sim_nav.csv` | 净值曲线 |
| `sim_positions.csv` | 当前持仓 |
| `sim_trades.csv` | 交易记录 |
