# 信号命中 vs 最终落桶 分离计划 — 2026-03-25

目标：
- 研究层：允许一个样本同时命中 B1 / B2 / 砖型图等多个标签
- 展示层：仍保留单桶归类，方便日常输出

原因：
- 当前 if/elif 路由会导致前序桶抢走后续桶样本
- B1 / B2 / 砖型图研究结果会被互相污染

实施方向：
1. 新增 signal hit 字段：
   - hit_b1
   - hit_b1_perfect
   - hit_b1_standard
   - hit_b1_weak
   - hit_b2
   - hit_brick
   - hit_single_pin
2. 回测/验证优先按 hit 标签统计
3. tactic_bucket 继续保留为展示层单桶输出
