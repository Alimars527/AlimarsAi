# 战术桶专用样本入口改造计划 — 2026-03-23

## 当前问题
现有 refined tactic grouped backtest 先跑“主线趋势”信号，再贴桶标签，导致：
- 单针下20
- 砖型图
- B2
- 主题类桶
难以独立形成样本。

## 改造目标
建立“按战术信号直接建样本”的入口，不再依赖主线趋势先过滤。

## 第一版做法
1. 对每只股票直接准备日线 + tactic indicators + B1/B2 + 单针 + 砖型图字段
2. 读取最新一日信号字段，直接 route_tactic
3. 以未来1日收益/退出收益做统一评估
4. 输出真正按战术桶聚合的结果

## 预期收益
让 theme_single_pin_low20 / theme_brick_exec / theme_b2_attack 等桶有机会真正独立成样本层。
