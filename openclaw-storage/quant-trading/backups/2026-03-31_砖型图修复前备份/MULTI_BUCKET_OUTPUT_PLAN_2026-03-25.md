# 多桶同时出现改造计划 — 2026-03-25

目标：一个样本若同时满足多个桶条件，则在研究/展示输出里同时出现在多个桶中。

## 实施
1. route_tactic 保留主桶 `tactic_bucket` 兼容旧逻辑
2. 新增 `tactic_buckets` 数组，收集所有命中桶
3. 回测统计对 `tactic_buckets` 做 explode 后按桶统计
4. 继续保留 `by_hit` 作为信号层统计
