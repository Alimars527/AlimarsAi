# OUTPUTS_INDEX.md

> `quant-trading/outputs/` 输出文件总索引
> 更新日期：2026-04-16

## 一、最新产出（2026-04-16）

### V5-T1 冠军策略回测
| 文件 | 说明 |
|---|---|
| `sim_replay_20230101_brick_v5_tier1_summary.json` | **V5-T1 冠军（+181.50%）** |
| `sim_replay_20230101_brick_v5_tier1_trades.csv` | V5-T1 交易明细 |
| `sim_replay_20230101_brick_v5_tier1_nav.csv` | V5-T1 净值曲线 |

### V5 版本对比实验
| 文件 | 说明 |
|---|---|
| `sim_replay_20230101_brick_v6_realestate_summary.json` | V6（15行业排除，+180.44%，已否决） |
| `sim_replay_20230101_brick_v7_b1_resonance_hard_summary.json` | V7 硬门控（21笔/-0.63%，失败） |
| `sim_replay_20230101_brick_v7_b1_resonance_soft_summary.json` | V7 软加分（+172.57%，失败） |

### 每日复盘
| 文件 | 说明 |
|---|---|
| `latest_plan.md` | 最新复盘报告 |
| `latest_summary.json` | 最新复盘摘要 JSON |

---

## 二、砖型图系列（历史）

### V4 行业过滤实验
| 文件 | 说明 |
|---|---|
| `sim_replay_...brick_v4_industry_blacklist_10_summary.json` | V4 10行业黑名单（+251.79%） |

### V3 基线
| 文件 | 说明 |
|---|---|
| `sim_replay_...strict_brick_v3_only_summary.json` | 砖型图 V3 单独（+101.64%） |
| `sim_replay_...strict_brick_v3_dynamic_exit_bridge_summary.json` | 砖型图动态退出桥接 |
| `sim_replay_...strict_brick_v3_keep_rotation_remove_omav_bridge_summary.json` | 砖型图去 OMAV 桥接 |

---

## 三、B1 系列已归档

### V4-A 主线（历史最强B1，已关闭）
| 文件 | 说明 |
|---|---|
| `sim_replay_...b1_prev2_structure_filter_v2a_summary.json` | V4-A 本体（+181.92%） |
| `sim_replay_...v4a_plus_avg5_band_1_2_deweight_05_v1_summary.json` | V4-A+avg5（+192.77%） |
| `sim_replay_...v4a_plus_avg5_band_1_2_deweight_05_narrowfix_v1_summary.json` | 窄修正尝试 |

### B1 早期实验
| 文件 | 说明 |
|---|---|
| `sim_replay_...b1_experimental_v1_summary.json` | B1 实验版 V1（153.80%） |
| `sim_replay_...b1_experimental_v2_summary.json` | B1 实验版 V2（83.43%） |
| `sim_replay_...b1_rr_filter_*` | RR 过滤系列 |
| `sim_replay_...b1_space_filter_*` | 空间过滤系列 |
| `sim_replay_...b1_forward_rotation_*` | 前向轮动 |

---

## 四、组合策略回测（历史）

| 文件 | 说明 |
|---|---|
| `sim_replay_20230101_summary.json` | 主版本 |
| `sim_replay_20230101_planB_summary.json` | Plan B |
| `sim_replay_20230101_drawdown_guard_summary.json` | 回撤保护版 |
| `sim_replay_20230101_position_tiered_summary.json` | 分仓版 |

---

## 五、任务/诊断产出

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
