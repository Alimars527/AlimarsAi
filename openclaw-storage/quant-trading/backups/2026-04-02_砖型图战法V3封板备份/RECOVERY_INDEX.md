# 恢复索引（极简版）

如果会话中断、换模型、上下文丢失，按这个顺序恢复：

## 1. 先看这三个文件
1. `quant-trading/PROJECT_STATE_BACKUP_2026-03-18.md`
2. `quant-trading/config/holdings.yaml`
3. `quant-trading/outputs/latest_plan.md`

## 2. 当前项目处于什么阶段
- 当前阶段：**第一阶段收尾优化**
- 节点计划：**周五收盘后进入第二阶段（数据回测搭建）**

## 3. 当前系统定位
- 收盘后人工触发复盘
- 用户手动同步持仓
- 系统输出：复盘摘要 + 候选池 + 次日执行卡

## 4. 用户关键偏好
- 房地产相关方向：**无论走势如何一律不做**
- 交易模式：日频、隔日交易、次日人工执行
- 当前不做：自动下单 / 高频 / 分钟级盘中策略

## 5. 当前持仓（以 holdings.yaml 为准）
- 兆易创新（603986.SH）
- 环旭电子（601231.SH）

## 6. 周五前的默认任务
继续优化第一阶段：
- 候选池收口
- 板块轮动贴合偏好
- 持仓动作建议和触发条件
- 买入区间校准

## 7. 周五后的默认任务
- 做本周最后一次日复盘
- 做第一阶段收口总结
- 进入第二阶段：数据回测搭建

## 8. 快速复盘运行命令
```bash
python3 /Users/alimars/.openclaw/workspace/quant-trading/scripts/run_daily_pipeline.py
```

## 9. 持仓修改命令
新增/更新：
```bash
python3 /Users/alimars/.openclaw/workspace/quant-trading/scripts/update_holdings.py --code 603986.SH --name 兆易创新 --cost 287.551 --quantity 1
```

删除：
```bash
python3 /Users/alimars/.openclaw/workspace/quant-trading/scripts/remove_holding.py --code 603123.SH
```
