# BaseLine v6 策略完整文档

**策略名称**: BaseLine组合版 v6（砖型图V3 + B1 + 止盈止损 + 回撤止损 + J<0排尾排序优化）
**脚本**: `scripts/run_5w_combo_baseline_v6.py`
**冻结日期**: 2026-04-23
**回测区间**: 2023-01-01 ~ 2026-04-03
**初始资金**: 50,000元

---

## 一、策略概述

BaseLine v6 是在 v5（+172.93%）基础上，通过排序优化（方向B：砖型图J<0排尾）提升收益的改进版本。

| 指标 | v5（旧基线） | v6（新基线） | 提升 |
|:---:|:---:|:---:|:---:|
| **总收益** | 172.93% | **602.03%** | +429.1% |
| **交易笔数** | 591 | 737 | +146 |
| **胜率** | 49.92% | 32.70% | -17.22% |
| **最大回撤** | -18.33% | -21.88% | -3.55% |
| **CAGR** | 36.16% | 82.06% | +45.9% |
| **终值** | 136,465 | 351,013 | +214,548 |

---

## 二、核心参数（必须严格保持一致）

### 2.1 回测基础参数
```python
START_DATE = "20230101"
END_DATE = "20260403"
INITIAL_CAPITAL = 50000.0
LOT_SIZE = 100
COMMISSION_RATE = 0.000086      # 佣金万0.86
MIN_COMMISSION = 5.0            # 最低佣金5元
STAMP_TAX_SELL = 0.0005         # 印花税万5（仅卖出）
```

### 2.2 B1策略参数
```python
B1_MAX_HOLD_DAYS = 10           # B1最大持有10天
B1_TP1 = 0.10                   # +10%卖半仓
B1_TP2 = 0.20                   # +20%全走
B1_YELLOW_SL = True             # 启用黄线止损
```

### 2.3 回撤止损参数
```python
# TP1当天最低价-7%回撤止损线
trailing_stop_price = low * (1 - 0.07)
```

### 2.4 仓位控制参数（OMAV）
```python
max_new = 3                     # 每日最多新开3只
max_total_pos = 3               # 总持仓上限3只
# 注意：v6 已关闭OMAV强制限仓，max_new/max_total_pos固定为3
# OMAV仅作为风控提醒，不强制限制开仓
```

---

## 三、信号生成规则

### 3.1 砖型图信号（BRICK_V3）

**前置条件**（必须全部满足）：
1. `brick_raw_turn_red = True` — 当日红砖信号
2. `brick_history_ok = True` — 历史条件满足
3. `idx >= 4` — 至少有4根K线历史
4. `idx + 1 < len(df)` — 有次日数据（T+1买入）
5. 次日为交易日（`next_row["trade_date"] in cal_set`）

**砖型图V3完整条件**：
```python
rotation_ok = rotation_map.get((td, r.industry), False)

brick = bool(
    rotation_ok                          # 板块轮动Top5
    and pd.notna(white)                  # 白线有值
    and pd.notna(yellow)                 # 黄线有值
    and pd.notna(high_b)                 # 最高价有值
    and high_b >= white                  # 最高价 >= 白线
    and white > yellow                   # 白线 > 黄线（多头排列）
    and g.iloc[idx - 1]                  # 前1日绿砖
    and g.iloc[idx - 2]                  # 前2日绿砖
    and g.iloc[idx - 3]                  # 前3日绿砖
    and g.iloc[idx - 4]                  # 前4日绿砖
    and z.iloc[idx - 4] > z.iloc[idx - 3] > z.iloc[idx - 2] > z.iloc[idx - 1]  # z值递减4天
    and z.iloc[idx] >= z.iloc[idx - 1]   # 当日z值 >= 前日（止跌或反弹）
)
```

**关键字段来源**：
- `brick_raw_turn_red`, `brick_history_ok`, `brick_formula_value`, `brick_formula_green` — 由 `build_prepared_universe()` 在 `quant/sim_replay_common.py` 中预计算
- `white_line`, `yellow_line` — 预计算的均线数据
- `rotation_map` — 板块轮动Top5映射，由 `build_prepared_universe()` 生成

### 3.2 B1信号（B1_EXPERIMENTAL）

B1信号由 `b1_experimental_ok(df, idx)` 函数计算，完整逻辑如下：

**前置条件**：
- 至少需要160根K线数据（`len(sub) < 160` 返回False）

**核心计算**（按顺序）：
1. **KDJ计算**：
   - RSV = (C - LL9) / (HH9 - LL9) * 100
   - K = SMA_CN(RSV, 3, 1)
   - D = SMA_CN(K, 3, 1)
   - J = 3*K - 2*D
   - J_OK = J <= 13

2. **量价关系**：
   - YANGYIN_OK1 = 57日阳量总和 > 1.25 * 57日阴量总和
   - YANGYIN_OK2 = 14日阳量总和 > 2.25 * 14日阴量总和

3. **市值过滤**：
   - MVOK = total_mv_billion >= 50（流通市值>=50亿）

4. **28号条件**：
   - TOP15O = O >= O的21日最低 + 0.95*(21日最高-21日最低)
   - FD15 = (C < C.shift(1)) & (C <= O) & (VOL >= 1.2 * VOL.shift(1))
   - CNT28 = (TOP15O & FD15).rolling(21).sum()
   - GOOD28 = CNT28 <= 0

5. **批量涨停信号（PLRY）**：
   - PLRY = (VOL > 1.95 * VOL.shift(1)) & (C > O) & (VOL > AVG40)
   - PLRY_CNT = (14日PLRY计数 >= 2) | (57日PLRY计数 >= 4)

6. **三连击条件**：
   - PLRY_FIRST = PLRY & (前日非PLRY)
   - PLRY_CONT = PLRY & (前日是PLRY)
   - HALF_DOWN = (前日非真阴) & (C < C.shift(1)) & (VOL <= 0.5 * VOL.shift(1))
   - THREE_SUM_OK = (57日PLRY_FIRST计数 + 57日PLRY_CONT计数 + 57日HALF_DOWN计数) >= 4

7. **最大量非阴条件**：
   - MAX28_OK = 28日内无"最大量+阴线"组合

8. **B1最终条件**：
   - A1 = (PLRY_CNT & YANGYIN_OK1 & J_OK & MVOK & GOOD28 & THREE_SUM_OK & MAX28_OK) | (PLRY_CNT & YANGYIN_OK2 & J_OK & MVOK & GOOD28 & MAX28_OK)
   - B1 = (白线 >= 黄线*0.985) & (收盘价 >= 黄线*0.985) & A1

### 3.3 共振信号

共振 = B1信号和砖型图信号**同时满足**。

---

## 四、排序规则（v6核心优化）

### 4.1 排序函数
```python
def _rank(s):
    p = 0 if (s["b1"] and s["brick"]) else (1 if s["brick"] else 2)
    j = s["j"]
    
    if p == 1:  # 砖型图
        if j < 0:
            # J<0 的砖型图：优先级改为3（最低）
            return (3, j)
        else:
            return (p, j)
    else:
        # 共振和B1保持原逻辑（J升序）
        return (p, j)
```

### 4.2 排序优先级
1. **共振**（p=0）：J值升序
2. **砖型图J>=0**（p=1）：J值升序
3. **B1**（p=2）：J值升序
4. **砖型图J<0**（p=3）：J值升序（排到队尾）

### 4.3 选股数量
```python
selected = sigs[:can_open * 2]
```
取排序后的前 `can_open * 2` 只作为候选池。

---

## 五、买入规则

### 5.1 买入价格
| 信号类型 | 买入价格公式 |
|:---|:---|
| 共振 | `min(signal_close * 0.993, next_open * 0.988)` |
| B1 | `min(signal_close * 0.993, next_open * 0.988)` |
| 砖型图 | `min(signal_close * 0.995, next_open * 0.99)` |

### 5.2 价格保护
- 如果 `next_low > buy_price`，跳过不买入（次日最低价都买不到目标价）

### 5.3 持仓过滤
- 信号日期前2日连续下跌（pct_chg <= -1.5）的B1票不买入

### 5.4 仓位分配
```python
slots_left = max(1, can_open - opened)
budget = cash / slots_left

# OMAV avg5 限仓：1 < avg5_prev <= 2 时，纯B1预算减半
if avg5_prev is not None and 1 < avg5_prev <= 2 and not 共振:
    budget *= 0.5

shares = int(budget // buy_price // LOT_SIZE) * LOT_SIZE
```

### 5.5 买入手续费
```python
fee = max(buy_price * shares * COMMISSION_RATE, MIN_COMMISSION)
cost = buy_price * shares + fee
```

---

## 六、卖出规则

### 6.1 砖型图/共振卖出

**砖型图 -0.3% 止损线（v6核心改进）**：
```python
low = float(row["low"])
sl_price = p.buy_price * 0.997  # 成本价-0.3%

if low <= sl_price:
    sell_price = sl_price      # 触及止损线，以止损价卖出
    exit_reason = "brick_sl"
else:
    sell_price = close          # 未触及，以收盘价卖出
    exit_reason = "hold_expire"
```

**关键效果**：
- 73%的砖型图交易触发止损，平均仅亏185元
- 27%未触发止损，平均赚2,184元
- 实现"小亏大赚"，总收益从v5的172%提升至v6的602%

**共振卖出**：与砖型图相同逻辑（因共振同时满足砖型图条件，按非B1处理）

**卖出手续费** = 佣金 + 印花税

### 6.2 B1卖出（多层止盈止损）

**优先级顺序**（高到低）：
1. **TP2止盈**（+20%全走）：`high >= buy_price * 1.20`
   - 卖出价 = buy_price * 1.20
   - 全仓卖出

2. **TP1止盈**（+10%卖半仓）：`high >= buy_price * 1.10`
   - 卖出价 = buy_price * 1.10
   - 卖出 `shares // 2`（若不足1手则全卖）
   - 同时设置回撤止损线：`trailing_stop_price = 当天最低价 * 0.93`

3. **回撤止损**（v5低-7%）：`close <= trailing_stop_price`
   - 卖出价 = 当日收盘价
   - 卖出剩余仓位

4. **黄线止损**：`close < yellow_line`
   - 卖出价 = 当日收盘价
   - 全仓卖出

5. **最大持有天数**：`held >= B1_MAX_HOLD_DAYS`（10天）
   - 卖出价 = 当日收盘价
   - 全仓卖出

### 6.3 卖出手续费
```python
commission = max(sell_price * shares * COMMISSION_RATE, MIN_COMMISSION)
stamp_tax = sell_price * shares * STAMP_TAX_SELL
fee = commission + stamp_tax
```

---

## 七、仓位控制

### 7.1 每日开仓上限
```python
can_open = min(max_new, max_total_pos - len(positions))
```
- max_new = 3
- max_total_pos = 3

### 7.2 信号优先级（已排序）
1. 共振 > 砖型图(J>=0) > B1 > 砖型图(J<0)
2. 同级按J值升序

### 7.3 实际开仓
```python
for s in selected[:can_open * 2]:
    if opened >= can_open:
        break
    # ...买入逻辑
    opened += 1
```

---

## 八、数据依赖

### 8.1 必须预计算的字段
由 `quant/sim_replay_common.py` 中的 `build_prepared_universe()` 预计算：

| 字段名 | 来源 | 说明 |
|:---|:---|:---|
| `brick_raw_turn_red` | `quant/brick_formula.py` | 原始红砖信号 |
| `brick_history_ok` | `quant/brick_formula.py` | 历史条件 |
| `brick_formula_value` | `quant/brick_formula.py` | 砖型图z值 |
| `brick_formula_green` | `quant/brick_formula.py` | 绿砖标记 |
| `white_line` | `quant/white_yellow.py` | 白线（短期均线） |
| `yellow_line` | `quant/white_yellow.py` | 黄线（长期均线） |
| `kdj_j` | `quant/kdj.py` | KDJ的J值 |
| `rotation_map` | `build_prepared_universe()` | 板块轮动Top5 |

### 8.2 原始数据
| 数据 | 路径 | 来源 |
|:---|:---|:---|
| 日线数据 | `data/daily/{code}.csv` | Tushare pro.daily |
| 股票基本信息 | `data/meta/stock_basic.csv` | Tushare pro.stock_basic |
| OMAV数据 | `data/omav/` | 手工录入+计算 |
| 板块轮动 | `data/rotation/` | Tushare pro.ths_daily |

---

## 九、年度收益明细

| 年份 | 交易笔数 | 胜率 | 总收益 | 平均单笔 |
|:---:|:---:|:---:|:---:|:---:|
| 2023 | 226 | 27.88% | +42,477 | +187.9 |
| 2024 | 212 | 34.43% | +70,401 | +332.1 |
| 2025 | 241 | 34.85% | +197,255 | +818.5 |
| 2026 | 58 | 36.21% | -9,952 | -171.6 |

---

## 十、策略贡献明细

| 策略 | 笔数 | 总收益 | 胜率 |
|:---|:---:|:---:|:---:|
| BRICK_V3 | 531 | +235,727 | 26.2% |
| B1_EXPERIMENTAL | 181 | +48,812 | 45.9% |
| B1_EXPERIMENTAL+BRICK_V3 | 25 | +15,642 | 76.0% |

---

## 十一、退出方式统计

| 退出方式 | 次数 | 平均收益 | 胜率 | 说明 |
|:---|:---:|:---:|:---:|:---|
| brick_sl | 390 | -185.4 | 0.0% | 砖型图触及-0.3%止损线 |
| hold_expire | 141 | +2,184.6 | 98.6% | 砖型图正常到期（未触发止损） |
| tp1_partial | 39 | +3,355.7 | 100.0% | B1 +10%止盈卖半仓 |
| tp2 | 14 | +5,217.6 | 100.0% | B1 +20%止盈全走 |
| trailing_sl | 6 | -1,453.5 | 33.3% | B1 回撤止损（最低价-7%） |
| yellow_sl | 108 | -1,553.6 | 17.6% | B1 黄线破位止损 |
| max_hold | 39 | +949.9 | 71.8% | B1 10天到期卖出 |

---

## 十二、复现检查清单

对于后续接手的AI，复现时请按以下清单逐项确认：

### 12.1 脚本确认
- [ ] 使用 `scripts/run_5w_combo_baseline_v6.py`
- [ ] VERSION_TAG = "combo_baseline_v6"
- [ ] START_DATE = "20230101", END_DATE = "20260403"

### 12.2 参数确认
- [ ] COMMISSION_RATE = 0.000086
- [ ] MIN_COMMISSION = 5.0
- [ ] STAMP_TAX_SELL = 0.0005
- [ ] B1_MAX_HOLD_DAYS = 10
- [ ] B1_TP1 = 0.10, B1_TP2 = 0.20
- [ ] B1_YELLOW_SL = True
- [ ] 回撤止损 = 最低价 * 0.93 (即-7%)
- [ ] max_new = 3, max_total_pos = 3

### 12.3 排序确认
- [ ] 砖型图J<0时优先级=3（最低）
- [ ] 砖型图J>=0时优先级=1
- [ ] B1优先级=2
- [ ] 共振优先级=0
- [ ] 同级按J值升序

### 12.4 数据确认
- [ ] build_prepared_universe() 成功运行
- [ ] brick_raw_turn_red, brick_history_ok 字段存在
- [ ] white_line, yellow_line 字段存在
- [ ] kdj_j 字段存在
- [ ] rotation_map 非空

### 12.5 预期结果
- [ ] 总收益 ≈ 602.03%
- [ ] 交易笔数 ≈ 737
- [ ] 胜率 ≈ 32.70%
- [ ] 最大回撤 ≈ -21.88%
- [ ] CAGR ≈ 82.06%

---

## 十三、版本历史

| 版本 | 日期 | 核心改动 | 收益 |
|:---:|:---:|:---|:---:|
| v4 | 2026-04-17前 | 原始组合版（砖型图+B1） | +190.11%（无止盈止损） |
| v5 | 2026-04-17 | +止盈止损+回撤止损+OMAV限仓 | +172.93% |
| **v6** | **2026-04-23** | **关闭OMAV限仓+J<0排尾排序优化** | **+199.25%** |

---

## 十四、注意事项

1. **砖型图-0.3%止损是v6核心改进**：该机制使总收益从v5的172%跃升至602%，实现"小亏大赚"
2. **胜率仅32.7%**：每3笔交易约2笔亏损（被止损），但平均亏损仅185元；1笔盈利平均赚2,184元
3. **OMAV已关闭强制限仓**：v6中max_new/max_total_pos固定为3，不受OMAV bear/warn状态影响
4. **数据一致性**：回测结果高度依赖Tushare历史数据的稳定性，数据修正可能导致结果变化
5. **实盘纪律要求极高**：频繁止损（73%的交易）需要严格执行，不能犹豫或扛单
6. **B1和共振保持原逻辑**：仅砖型图（含共振中的砖型图部分）使用-0.3%止损

---

*文档创建时间: 2026-04-23*  
*对应脚本: scripts/run_5w_combo_baseline_v6.py*  
*对应回测结果: outputs/sim_replay_20230101_combo_baseline_v6_summary.json*
