# quant-trading

人工触发式收盘后量化复盘系统 + 模拟实盘验证。

> 项目已迁移到 **AiLab 工作区**。
> 当前真实位置：`/Volumes/Alimars扩容空间/AiLab/openclaw-workspace/quant-trading`
> 兼容访问路径：`/Users/alimars/.openclaw/workspace/quant-trading`（软链接）
> 最后更新：2026-04-16

## 冠军策略：砖型图 V5-T1

**当前唯一主线战法。B1路线已彻底放弃。**

| 指标 | 数值 |
|---|---|
| 总收益 | +181.50% |
| 交易笔数 | 552 |
| 胜率 | 52.17% |
| 最大回撤 | -13.65% |
| CAGR | 37.5% |
| PF | 1.55 |
| 回测期 | 2023-01-01 ~ 2026-03-31 |

**年度明细：** 2023 +22.0%(178笔) | 2024 +18.8%(131笔) | 2025 +88.4%(203笔) | 2026Q1 +3.1%(40笔)

**核心规则：** 砖型图信号 + 14行业黑名单排除
**策略文档：** `docs/strategies/BRICK_STRATEGY_V5_2026-04-16.md`
**回测脚本：** `scripts/run_simulated_paper_backtest_20230101_brick_v5_tier1.py`

### 已验证失败路线

| 路线 | 结果 | 结论 |
|---|---|---|
| V6（15行业排除） | +180.44% | 多排除房产服务无额外价值 |
| V7-B1共振硬门控 | 21笔/-0.63% | 信号稀疏，彻底失败 |
| V7-B1共振软加分 | +172.57% | 共振胜率35.7%，重仓亏损 |
| B1 V4-A+avg5 | +192.77% | 历史最强B1，已被V5超越 |

## 当前阶段：仓位评分系统

已确认设计方案（RR比3分+板块2分+趋势2分+量能2分+信号1分=满分10），待执行TaskA~E：
- TaskA：创建评分模块 `position_scorer.py`
- TaskB：模拟实盘接入评分
- TaskC：候选票推荐新增得分列
- TaskD：V5-T1回测接入评分+仓位
- TaskE：重跑回测对比

## 日常指令

| 指令 | 说明 |
|---|---|
| `@数据更新` | 收盘后同步全市场数据（5498只+指数） |
| `@复盘` | 每日复盘全流程 |
| `@候选票推荐` | 按V5-T1扫描，追加到日报 |
| `@模拟实盘` | T+1模拟交易执行 |
| `@reset` | 备份进度到引导文件 + 重连 |

## 模拟实盘

- 5万起始（2026-04-15开始）
- 状态文件：`config/simulated_portfolio.yaml`
- 费用：佣金万0.86 + 印花税万5
- 单票≤30%，最多3只

## 恢复优先读取文件

1. `AI_HANDOFF_GUIDE.md`（最全面）
2. `RECOVERY_INDEX.md`
3. `docs/DOCS_INDEX.md`
4. `outputs/OUTPUTS_INDEX.md`
5. `docs/strategies/BRICK_STRATEGY_V5_2026-04-16.md`
6. `config/holdings.yaml`
7. `config/simulated_portfolio.yaml`

## 手动环境数值更新流程

- 当用户提供OMAV/活跃市值时，写入：
  - 历史表：`data/manual_inputs/market_activity_history.csv`
  - 最新值：`data/manual_inputs/market_activity_latest.json`

## 目录结构

- `config/`：配置（holdings.yaml、simulated_portfolio.yaml）
- `quant/`：核心策略/回测代码
- `scripts/`：运行脚本
- `outputs/`：结果输出（见 OUTPUTS_INDEX.md）
- `reports/`：日报与战法分析
- `reports/daily/`：每日复盘成品
- `docs/strategies/`：策略文档（V5冠军策略在此）
- `docs/phase/`：阶段计划
- `docs/research/`：研究笔记
- `data/`：数据目录（软链接到扩容盘）
- `backups/`：备份目录
