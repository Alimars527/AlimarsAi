# BACKTEST_PROGRESS_TEMPLATE_V1（2026-04-10）

## 一、适用范围
- 所有未来的中长回测脚本
- 所有分年 / 分月 / 单策略 / 组合策略回测
- 所有需要运行超过短时交互窗口的重计算任务

## 二、进度文件要求
每个长回测脚本默认必须输出一个 `progress.json`，至少包含以下字段：

```json
{
  "task": "backtest_task_name",
  "status": "running",
  "processed": 120,
  "total": 786,
  "progress_pct": 15.27,
  "updated_at": "2026-04-10T18:00:00+08:00",
  "current_trade_date": "20240115",
  "message": "processing 20240115"
}
```

### 最低必需字段
- `task`
- `status`
- `processed`
- `total`
- `progress_pct`
- `updated_at`

### 推荐附加字段
- `current_trade_date`
- `message`
- `ok`
- `fail`

---

## 三、状态约定
- `running`：运行中
- `done`：已完成
- `error`：异常结束
- `stopped`：人工停止

---

## 四、文件命名规范
统一使用：

- `outputs/<script_base_name>_progress.json`

例如：
- `outputs/sim_replay_20230101_b1_prev2_structure_filter_v2a_progress.json`

---

## 五、收尾要求
### 完成后
- 若该进度文件仅用于临时显示进度：**完成后删除**
- 若该任务需要保留最终状态记录：可改写为 `done` 后保留，但默认仍优先删除

### 中断后
- 若需要断点续跑，应额外保留：
  - `state.json`
  - 或可恢复的游标信息

---

## 六、实现原则
- 每处理一批或每隔固定数量更新一次进度
- 避免每条样本都刷盘，防止 IO 过重
- 进度更新频率以“人类可读、系统开销可控”为准

---

## 七、一句话规则
**今后所有长回测脚本，默认带 `progress.json`；完成后默认清理临时进度文件。**
