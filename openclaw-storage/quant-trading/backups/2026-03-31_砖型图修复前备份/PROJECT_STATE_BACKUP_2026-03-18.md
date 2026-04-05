# Quant Trading 项目本地备份

更新日期：2026-03-18
状态：第一阶段已基本成型，周五收盘后进入第二阶段（数据回测搭建）

---

## 一、项目目标

当前项目定位为：
**人工触发式收盘后量化复盘系统**

核心流程：
1. 用户在收盘后手动发起复盘
2. 用户手动同步当前持仓（新增/删除/成本/手数）
3. 系统拉取日线数据并完成复盘
4. 系统输出：
   - 日终复盘摘要
   - 板块轮动结论
   - 持仓复盘
   - 候选股
   - 次日交易执行卡

当前不做：
- 自动定时复盘
- 自动下单
- 高频/分钟级策略
- 盘中量化交易

---

## 二、用户已明确的关键偏好

### 1. 交易模式
- 日频
- 收盘后复盘
- 次日人工执行
- 主打隔日交易 / 短波段

### 2. 数据使用方式
- 不依赖 Google Sheets 作为核心持仓源
- 用户手动告知持仓变化
- 系统本地维护持仓文件

### 3. 明确排除方向
- **房地产相关方向无论走势如何，一律不做**
  已纳入偏好过滤：
  - 区域地产
  - 全国地产
  - 房产服务
  - 园区开发
  - 其他商业

### 4. 偏好方向（当前系统偏好）
- 半导体
- 元器件
- 电气设备
- 医药商业
- 化学制药
- 白酒
- 消费电子
- 软件服务

---

## 三、当前持仓（截至 2026-03-18）

当前持仓：
- 兆易创新（603986.SH）
  - 成本：287.551
  - 手数：1
- 环旭电子（601231.SH）
  - 成本：41.47
  - 手数：1

已确认：
- **翠微股份（603123.SH）已不再持有**，已从本地持仓配置移除。

---

## 四、第一阶段已完成的模块

### 1. 项目骨架
目录：`quant-trading/`

主要目录结构：
- `config/`
- `data/`
- `reports/`
- `scripts/`
- `quant/`
- `outputs/`

### 2. 配置与持仓管理
已完成：
- `config/settings.yaml`
- `config/holdings.yaml`
- `config/strategy.yaml`
- `config/preferences.yaml`

支持：
- 手动更新持仓
- 删除持仓
- 聊天式持仓变更解析（基础版）

### 3. 数据模块
已完成：
- Tushare 日线拉取
- 指数日线拉取
- daily_basic
- stock_basic
- 板块/概念基础接口可调用验证

### 4. 市场环境判断
已完成基础版：
- 指数强弱判断
- 强 / 中 / 弱 环境分类

### 5. 板块轮动模块
已完成基础结构：
- 当前主线（原始强度）
- 可能延续
- 可埋伏观察
- 回避方向

已知问题：
- 仍偏“原始数据强弱”，还需继续贴合用户审美
- 需要继续强化“原始强势板块”和“实战优先板块”的双层输出

### 6. 持仓复盘模块
已完成：
- 持仓盈亏统计
- 支撑/压力识别（改良版）
- 动作建议输出
- 高开/平开/低开三套预案
- 触发条件输出：
  - 跌破偏离场
  - 反抽减仓位
  - 站回继续持有位

### 7. 候选股筛选模块
已完成：
- 候选股过滤
- 主线候选 / 埋伏观察 / 技术备选分层
- 去除 ST
- 去除地产/房产类噪音行业
- 偏好行业加权
- 候选优先级排序
- 重点候选 / 观察候选 / 不建议追 分层

### 8. 执行适配模块
已完成：
- execution_style（执行属性）
- strategy_tag（主线趋势 / 轮动补涨 / 埋伏观察 / 技术备选）
- 不追高过滤
- 加速票不追逻辑

### 9. 买入区间校准模块（新近加入）
已完成第一版：
- 新增 `entry_calibrator.py`
- 不同类型候选票使用不同的建议区间逻辑：
  - 主线趋势票
  - 轮动补涨票
  - 强势加速票
  - 普通观察票
- 输出：
  - 建议区间
  - 不追价格线
  - 解释说明

该模块的加入原因：
此前系统曾出现候选方向判断对，但买入区间严重脱离现实交易区间的问题。

### 10. 日报输出模块
已完成：
- `outputs/latest_plan.md`
- `outputs/latest_summary.json`
- 日终复盘摘要
- 次日交易计划

---

## 五、已经沉淀的重要经验

### 1. 候选票推荐方向对，不代表买入区间合理
关键案例：
- 深圳华强：方向对，但历史给出的买入区间严重脱离实际
- 丽珠集团：推荐质量偏低，价格锚点与强度判断不够好
- 东北制药：买入区间基本可执行，但个股弹性不足

结论：
**第二阶段之前，第一阶段必须修正“买入区间校准”问题。**

### 2. 当前系统更适合做什么
当前系统本质上是：
**量化研究助手 / 收盘后决策辅助系统**

它适合：
- 缩小候选范围
- 稳定复盘流程
- 提供次日执行卡

它暂时不等于：
- 完整量化工程
- 已回测验证的强信号系统

### 3. 推荐票的默认观察周期
当前默认周期：
- 隔日 ~ 3日 为主
- 强势趋势票可看 3~5 日

不是中长线预测系统。

---

## 六、Tushare 权限现状

用户当前积分：2500
结论：**足够进入第二阶段**

已实测可调用成功的重要接口：
- daily
- daily_basic
- stock_basic
- trade_cal
- adj_factor
- stk_limit
- moneyflow
- concept
- concept_detail
- index_daily
- suspend_d
- limit_list_d
- hm_list
- fina_indicator
- income
- balancesheet
- cashflow
- express
- forecast
- top_list
- margin

结论：
- 暂时无需额外开权限
- 周五后可直接进入第二阶段
- 等第二阶段框架跑起来后，再看是否需要补权限

---

## 七、阶段性路线图

### 当前阶段：第一阶段收尾
周五前继续优化：
1. 持仓复盘
2. 候选池收口
3. 板块轮动贴合偏好
4. 执行卡与买入区间优化

### 计划节点：周五收盘后
执行：
1. 本周最后一次日复盘
2. 第一阶段收口总结
3. 正式进入第二阶段：数据回测搭建

### 第二阶段方向（已确定，但尚未开工）
目标：
- 不计代价和成本，优先搭建最好用、最精准、对预测最有帮助的回测系统

初步方向：
- 主线趋势策略回测
- 轮动补涨策略回测
- 埋伏观察策略回测
- 历史样本统计
- 胜率 / 盈亏比 / 最大回撤 / 市场环境适配度

---

## 八、关键文件清单

### 配置文件
- `/Users/alimars/.openclaw/workspace/quant-trading/config/settings.yaml`
- `/Users/alimars/.openclaw/workspace/quant-trading/config/holdings.yaml`
- `/Users/alimars/.openclaw/workspace/quant-trading/config/strategy.yaml`
- `/Users/alimars/.openclaw/workspace/quant-trading/config/preferences.yaml`

### 核心模块
- `quant/config.py`
- `quant/data_loader.py`
- `quant/market_regime.py`
- `quant/sector_rotation.py`
- `quant/rotation_analyzer.py`
- `quant/holdings_review.py`
- `quant/candidate_selector.py`
- `quant/full_market_scan.py`
- `quant/execution_filter.py`
- `quant/action_labels.py`
- `quant/entry_calibrator.py`
- `quant/priority_ranker.py`
- `quant/narrative.py`
- `quant/trade_planner.py`

### 脚本
- `scripts/run_daily_pipeline.py`
- `scripts/update_holdings.py`
- `scripts/remove_holding.py`
- `scripts/apply_holding_instruction.py`

### 输出
- `outputs/latest_plan.md`
- `outputs/latest_summary.json`

### 日志/经验沉淀
- `reports/logs/2026-03-18-notes.md`
- `PROJECT_STATE_BACKUP_2026-03-18.md`

---

## 九、如果未来上下文丢失，新会话应如何接续

新会话恢复时应先做：
1. 阅读本文件 `PROJECT_STATE_BACKUP_2026-03-18.md`
2. 阅读 `quant-trading/README.md`
3. 检查 `config/holdings.yaml` 当前持仓
4. 检查 `outputs/latest_plan.md` 最近一次输出
5. 用户若说“继续推进”，默认：
   - 周五前继续第一阶段优化
   - 周五收盘后进入第二阶段回测搭建

---

## 十、当前最重要的共识

- 第一阶段已经接近可封版
- 周五收盘后切第二阶段是合理节奏
- Tushare 当前权限足够，不需立刻额外补权限
- 房地产相关方向永久排除
- 当前系统是“收盘后复盘 + 次日执行卡”系统
- 后续会在稳定使用基础上进入真正量化回测阶段
