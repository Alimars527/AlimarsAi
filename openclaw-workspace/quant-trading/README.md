# quant-trading

人工触发式收盘后量化复盘系统。

> 项目已迁移到 **AiLab 工作区**。
> 当前真实位置：`/Volumes/Alimars扩容空间/AiLab/openclaw-workspace/quant-trading`
> 兼容访问路径：`/Users/alimars/.openclaw/workspace/quant-trading`（软链接）
> 最后更新：2026-04-14

## 当前目标
- 收盘后由用户手动触发复盘
- 本地维护持仓，不依赖 Google Sheets
- 自动完成：市场环境分析、板块轮动、持仓复盘、次日预案

## 当前战法版本（核心）

### B1 进攻候选层
| 版本 | 状态 | 总收益 | 最大回撤 | 备注 |
|---|---|---:|---:|---|
| B1_V4_A 前两日结构过滤版 | 进攻基准 | 181.92% | -20.12% | 当前最干净主候选 |
| B1_V4_A_avg5_50 进攻增强版 | 当前最强 | 192.77% | -19.89% | avg5 50% 降权标准桥接 |
| B1_V3 位置质量过滤版 | 待重建稳健线 | 48.02% | -28.58% | 口径纯化后，已不适宜当强稳健候选 |

### 砖型图
| 版本 | 状态 | 总收益 | 备注 |
|---|---|---:|---|
| 严格砖型图 V3 | 正式冻结 | 101.64% | 单独跑依然很强 |

### 组合策略
| 版本 | 总收益 | 备注 |
|---|---:|---|
| B1实验版V1 + 严格砖型图 V3 | 134.13% | 严格组合基准 |
| B1实验版V1 + 严格砖型图 V3 + avg5 轻降权 | 179.13% | 方向验证成功 |

### 当前研究阶段：窄修正
- 保住 192.77% 主体
- 处理 2023 副作用（新增差纯 B1 单）
- 不动砖型图腿、共振单、avg5 降权力度

## 使用方式
1. 用户告知"开始复盘"并同步最新持仓
2. 更新 `config/holdings.yaml`，或使用脚本：
   - 新增/更新：`python3 scripts/update_holdings.py --code 603986.SH --name 兆易创新 --cost 287.551 --quantity 1`
   - 删除：`python3 scripts/remove_holding.py --code 603986.SH`
3. 运行日终流水线：`python3 scripts/run_daily_pipeline.py`
4. 输出 markdown 日报 + json 摘要

## 恢复优先读取文件
如果发生上下文丢失/换模型/会话中断，优先读取：
1. `AI_HANDOFF_GUIDE.md`（最全面）
2. `RECOVERY_INDEX.md`
3. `docs/DOCS_INDEX.md`
4. `outputs/OUTPUTS_INDEX.md`
5. `config/holdings.yaml`
6. `outputs/latest_plan.md`

## 手动环境数值更新流程（重要）
- 当用户手动提供类似"市场活跃市值"这类环境数值时，必须同步写入本地文件
- 历史表：`data/manual_inputs/market_activity_history.csv`
- 最新值：`data/manual_inputs/market_activity_latest.json`

## 目录结构（2026-04-14 更新）
- `config/`：配置
- `quant/`：核心策略/回测代码
- `scripts/`：运行脚本
- `outputs/`：结果输出（见 OUTPUTS_INDEX.md）
- `reports/`：日报与日志
- `reports/战法策略库/`：战法版本资料库（按 B1正式版 / 砖型图 / B1实验版 分目录管理）
  - 总入口：`reports/战法策略库/战法版本总表.md`
- `reports/战法回测对比/`：回测对比报告（4月12日集中产出了一批关键决策文档）
- `reports/daily/`：每日复盘成品
- `docs/strategies/`：正式策略文档、版本总结、执行口径
- `docs/phase/`：阶段计划、阶段总结
- `docs/research/`：研究笔记、验证笔记
- `docs/recovery/`：历史恢复索引与状态快照
- `docs/DOCS_INDEX.md`：文档总入口
- `data/`：数据目录（软链接到扩容盘）
- `backups/`：备份目录（软链接到扩容盘）
