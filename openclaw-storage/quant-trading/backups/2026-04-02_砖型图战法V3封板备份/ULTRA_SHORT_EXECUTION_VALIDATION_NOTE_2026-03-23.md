# 超短执行模型验证说明 — 2026-03-23

当前开始重跑 tactic bucket direct backtest，目标是验证：
- 单针下20
- 砖型图
在“隔日红优先、5%先跑、不涨撤、开盘观察后执行”的模型下是否改善。

要求：
- 继续使用断点式推进
- 保留 progress.json 和 state.jsonl
- 中断后直接续跑
