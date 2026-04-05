# 第二阶段进展备份（截至 2026-03-20）

## 当前状态
第二阶段已正式启动，并已从“规则草图”进入“本地历史数据 + 真实样本回测 + 执行层验证”阶段。

## 已完成内容

### 1. 回测总体规划
- 已创建 `PHASE2_BACKTEST_PLAN.md`
- 明确第二阶段目标：把第一阶段经验规则转化为可回测、可验证、可修正的研究框架

### 2. 回测配置与骨架
已创建：
- `config/backtest.yaml`
- `quant/strategy_rules.py`
- `quant/backtest_runner.py`
- `scripts/run_backtest.py`

### 3. 本地历史数据层
已创建：
- `quant/local_data_store.py`
- `quant/history_sync.py`
- `scripts/sync_history.py`
- `scripts/sync_history_resume.py`
- `scripts/backfill_history_resume.py`

已完成：
- 本地 `stock_basic`、`index_daily`、`daily`、`daily_basic`、`adj_factor` 数据仓基础结构
- 已完成全市场 2025-01-01 ~ 2026-03-20 的首轮本地化
- 已启动向前补数（2023-01-01 起）
- 具备断点续跑能力，状态文件写入 `data/meta/*.json`

### 4. 信号与回测模块
已创建：
- `quant/backtest_data.py`
- `quant/signal_engine.py`
- `quant/simulator.py`
- `quant/metrics.py`
- `quant/local_backtest.py`
- `quant/batch_backtest.py`
- `scripts/run_local_backtest_demo.py`
- `scripts/run_batch_backtest_demo.py`

已完成：
- 基于本地历史数据的真实样本单票回测
- 基于本地历史数据的批量样本回测
- 已接入手续费/印花税/最小佣金/lot size 可配置接口
- 费用配置来自 `config/backtest.yaml`

### 5. 买入区间回测
已创建：
- `quant/entry_backtest.py`
- 复用 `quant/entry_calibrator.py`

已完成：
- 建议买入区间是否触发的历史验证
- 下沿 / 中值 / 上沿三种成交假设回测

核心阶段性结论：
- 区间上沿最差
- 区间下沿优于中值和上沿
- 仅靠静态比例区间优化已出现边际递减

### 6. 次日执行场景建模
已创建：
- `quant/scenario_entry_backtest.py`

已完成：
- 区分 high_open / flat_open / low_open 三类次日开盘场景
- 已验证：不同开盘场景下的执行质量明显不同

阶段性结论：
- high_open 普遍更危险
- low_open 不天然等于便宜机会
- flat_open 在很多主线趋势样本里更接近合理执行场景
- 但 flat_open 更适合作为执行层过滤，而非信号层硬门槛

### 7. 卖点模型
已创建：
- `quant/exit_engine.py`
- `quant/exit_backtest.py`

已完成：
- 第一版规则化卖点模型：固定止盈、固定止损、次日弱收退出、最长持有日
- 第二版按“策略类型 + 开盘场景”细化卖点规则

阶段性结论：
- 卖点模型必须保留
- 当前卖点参数仍偏粗，尚未显著把整体收益拉正
- 不同开盘场景确实应使用不同退出逻辑

## 当前已验证出的方向
1. 行业偏好过滤有效
2. 指数环境过滤有效
3. 主线趋势规则收紧有效
4. 买点区间下沿优于中值和上沿
5. 次日执行场景应纳入模型
6. 卖点模型对最终结果影响很大，不能缺失

## 当前仍未完成的问题
1. 统一静态区间模型不够细
2. 卖点参数仍需继续打磨
3. 策略内部的“票性分层”还未接入
4. 长样本尚未补齐，当前很多验证仍主要基于近一年样本

## 当前推荐的下一步方向
- 在主线趋势内部增加“票性分层”（高弹性主线 / 稳定趋势主线 / 边缘趋势）
- 等历史补数更多完成后，做长样本复核
- 继续用当前近一年样本快速试错和调参
- 已形成第一版“行业 -> 优先策略”映射：
  - 元器件 -> 主线趋势优先
  - 电气设备 -> 主线趋势优先
  - 软件服务 -> 主线趋势次优先
  - 医药商业 -> 轮动补涨优先
  - 化学制药 -> 轮动补涨优先
- 主线趋势内部票性分层已进入阶段性可用状态：
  - 稳定趋势主线 -> 主线趋势-优先
  - 边缘趋势 -> 主线趋势-谨慎
  - 高弹性主线暂保留为辅助标签，不作为当前主分类核心
