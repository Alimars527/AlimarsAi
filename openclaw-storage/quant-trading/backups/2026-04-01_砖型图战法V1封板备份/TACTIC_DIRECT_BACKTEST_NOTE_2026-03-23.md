# 战术桶专用样本入口验证说明 — 2026-03-23

当前开始运行新的 direct tactic bucket backtest：
- 不再依赖“主线趋势”先过滤
- 直接按战术信号建样本

要求：
- 使用断点式推进
- 保留 progress.json 和 state.jsonl
- 中断后直接续跑
