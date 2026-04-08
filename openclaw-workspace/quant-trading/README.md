# quant-trading

人工触发式收盘后量化复盘系统。

> 项目已迁移到 **AiLab 工作区**。
> 当前真实位置：`/Volumes/Alimars扩容空间/AiLab/openclaw-workspace/quant-trading`
> 兼容访问路径：`/Users/alimars/.openclaw/workspace/quant-trading`（软链接）

## 当前目标
- 收盘后由用户手动触发复盘
- 本地维护持仓，不依赖 Google Sheets
- 自动完成：市场环境分析、板块轮动、持仓复盘、次日预案

## 第一版范围
- 本地配置与持仓管理
- Tushare 日线/指数数据拉取
- 市场概览
- 持仓复盘
- 候选股与次日交易计划输出

## 使用方式（V1）
1. 用户告知“开始复盘”并同步最新持仓
2. 更新 `config/holdings.yaml`，或使用脚本：
   - 新增/更新：`python3 scripts/update_holdings.py --code 603986.SH --name 兆易创新 --cost 287.551 --quantity 1`
   - 删除：`python3 scripts/remove_holding.py --code 603986.SH`
3. 运行日终流水线：`python3 scripts/run_daily_pipeline.py`
4. 输出 markdown 日报 + json 摘要

## 恢复优先读取文件
如果发生上下文丢失/换模型/会话中断，优先读取：
1. `RECOVERY_INDEX.md`
2. `docs/phase/PROJECT_STATE_BACKUP_2026-03-18.md`
3. `docs/recovery/STATE_SNAPSHOT.json`
4. `config/holdings.yaml`
5. `outputs/latest_plan.md`

## 手动环境数值更新流程（重要）
- 当用户手动提供类似“市场活跃市值”这类环境数值时，不能只在对话里记住，必须同步写入本地文件。
- 当前人工更新历史文件：`data/manual_inputs/market_activity_history.csv`
- 当前最新值文件：`data/manual_inputs/market_activity_latest.json`
- 处理原则：
  1. 收到用户新值 → 先更新历史表（按日期追加/更新）
  2. 同步更新 latest 文件
  3. 如后续确认与 OMAV 主流程口径完全一致，再考虑并入正式环境数据流程
- 目的：避免切换 AI / 上下文丢失后重复手工补录。

## 目录结构（2026-04-05 整理后）
- `config/`：配置
- `quant/`：核心策略/回测代码
- `scripts/`：运行脚本
- `outputs/`：结果输出
- `reports/`：日报与日志
- `reports/战法策略库/`：战法版本资料库（按 B1正式版 / 砖型图 / B1实验版 分目录管理，每个版本一个文件，另含《战法版本总表》）
- `docs/strategies/`：正式策略文档、版本总结、执行口径
- `docs/phase/`：阶段计划、阶段总结、项目状态文档
- `docs/research/`：研究笔记、验证笔记、专题计划
- `docs/recovery/`：历史恢复索引与状态快照
- `docs/DOCS_INDEX.md`：文档总入口
- `archive/root_backups/`：早期散落在根目录的单文件备份脚本
- `data/`：数据目录（已迁移到扩容盘并以软链接保留原路径）
- `backups/`：备份目录（已迁移到扩容盘并以软链接保留原路径）
