# PROJECT_STRUCTURE.md

本项目已迁移到扩容盘，原工作区路径保留为软链接，方便 OpenClaw 与其他 AI 按旧路径继续访问。

## 当前主路径
- 项目真实位置：`/Volumes/Alimars扩容空间/AiLab/openclaw-workspace/quant-trading`
- 兼容访问路径：`/Users/alimars/.openclaw/workspace/quant-trading`

## 目录结构说明
- `README.md`：项目总说明
- `RECOVERY_INDEX.md`：上下文恢复入口
- `PROJECT_STRUCTURE.md`：当前目录结构与迁移说明
- `config/`：配置文件
- `quant/`：核心策略/信号/回测代码
- `scripts/`：执行脚本
- `outputs/`：结果输出（根目录保留原文件，分类子目录多为软链接浏览）
- `reports/`：报告与审阅稿
  - `reports/obsidian_reviews/`：给 Obsidian 审阅的每日复盘成品
- `docs/`：文档中心
  - `docs/strategies/`：策略文档与版本口径
  - `docs/phase/`：阶段计划、阶段总结、每日复盘模板
  - `docs/research/`：研究笔记与专题验证
  - `docs/recovery/`：历史恢复材料与状态快照
  - `docs/DOCS_INDEX.md`：文档总索引
- `archive/`：历史散落备份文件归档
- `data/`：数据目录（软链接到扩容盘 data 存储）
- `backups/`：备份目录（软链接到扩容盘 backups 存储）

## AI 阅读顺序建议
1. `RECOVERY_INDEX.md`
2. `PROJECT_STRUCTURE.md`
3. `docs/DOCS_INDEX.md`
4. `outputs/OUTPUTS_INDEX.md`

## 注意事项
- 不要假设 `data/` 与 `backups/` 是普通目录，它们是软链接。
- 若要新增每日复盘成品，优先写入：`reports/obsidian_reviews/YYYY-MM-DD_每日复盘.md`
- 若要新增正式策略文档，优先写入：`docs/strategies/`
