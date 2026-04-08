# OUTPUTS_INDEX.md

安全整理说明：
- `outputs/` 根目录中的原始结果文件**未移动**，避免影响现有脚本路径。
- 新增的分类子目录使用**软链接**进行归类浏览。

## 分类目录
- `reviews/`：每日复盘相关输出
- `simulations/`：模拟盘/纸上实盘回放结果
- `repairs/`：数据修补、补丁、完整性修复、回填类结果
- `backtests/`：回测结果总表与批量回测输出
- `task_runs/`：B1/Brick 专项任务、条件拆解、收束优化、执行层复核
- `diagnostics/`：验证、诊断、样本检查、检查类结果
- `reference/`：总览/状态/进度参考文件

## 使用建议
- 人工查看时：优先从分类目录进入
- 脚本读取时：仍优先使用原始文件路径（兼容旧代码）

## 当前重点结果（新增）
- `sim_replay_20230101_b1_v3_position_quality_formal_candidate_summary.json`：B1_V3 位置质量过滤正式候选版结果
