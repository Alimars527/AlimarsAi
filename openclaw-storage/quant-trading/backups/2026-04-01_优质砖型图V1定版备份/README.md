# quant-trading

人工触发式收盘后量化复盘系统。

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
2. `PROJECT_STATE_BACKUP_2026-03-18.md`
3. `STATE_SNAPSHOT.json`
4. `config/holdings.yaml`
5. `outputs/latest_plan.md`
