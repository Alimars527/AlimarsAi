import csv
from collections import defaultdict

# === NAV Analysis ===
nav_path = "/Volumes/Alimars扩容空间/AiLab/openclaw-workspace/quant-trading/outputs/sim_replay_20230101_brick_v5_tier1_nav.csv"
rows = []
with open(nav_path, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows.append(row)

# Max Drawdown
peak = float(rows[0]["total_equity"])
max_dd = 0
max_dd_start = ""
max_dd_end = ""
dd_start = ""
dd_peak = peak

for row in rows:
    eq = float(row["total_equity"])
    date = row["trade_date"]
    if eq > peak:
        peak = eq
        dd_peak = peak
        dd_start = date
    dd = (peak - eq) / peak * 100
    if dd > max_dd:
        max_dd = dd
        max_dd_start = dd_start
        max_dd_end = date

# Annual breakdown
year_equity = defaultdict(list)
for row in rows:
    year = row["trade_date"][:4]
    year_equity[year].append(float(row["total_equity"]))

print("=" * 55)
print("砖型图 V5-T1 修复后真实回测数据")
print("=" * 55)
print("期间: 2023-01-03 ~ 2026-04-03 (约3.25年)")
print("初始: 100,000 | 期末: %s" % rows[-1]["total_equity"])
print("总收益: +181.50%")
print("最大回撤: %.2f%% (%s ~ %s)" % (max_dd, max_dd_start, max_dd_end))
print()

prev_eq = 100000.0
for year in sorted(year_equity.keys()):
    end_eq = year_equity[year][-1]
    ret = (end_eq / prev_eq - 1) * 100
    print("%s: %10.0f -> %10.0f | 年收益: %+7.1f%%" % (year, prev_eq, end_eq, ret))
    prev_eq = end_eq

years = 3 + 3.0/12
cagr = (float(rows[-1]["total_equity"]) / 100000) ** (1.0/years) - 1
print()
print("复合年化(CAGR): %.1f%%" % (cagr * 100))

# Per-year max drawdown
print()
print("年度最大回撤:")
for year in sorted(year_equity.keys()):
    eqs = year_equity[year]
    pk = eqs[0]
    ydd = 0
    for e in eqs:
        if e > pk:
            pk = e
        dd = (pk - e) / pk * 100
        if dd > ydd:
            ydd = dd
    print("  %s: %.2f%%" % (year, ydd))

# === Trade Stats ===
trades_path = "/Volumes/Alimars扩容空间/AiLab/openclaw-workspace/quant-trading/outputs/sim_replay_20230101_brick_v5_tier1_trades.csv"
with open(trades_path, "r", encoding="utf-8-sig") as f:
    trades = list(csv.DictReader(f))

wins = [float(t["net_pnl"]) for t in trades if float(t["net_pnl"]) > 0]
losses = [float(t["net_pnl"]) for t in trades if float(t["net_pnl"]) < 0]

total_win = sum(wins)
total_loss = abs(sum(losses))
avg_win = total_win / len(wins) if wins else 0
avg_loss = total_loss / len(losses) if losses else 0

print()
print("盈亏结构:")
print("  盈利: %d笔 | 亏损: %d笔 | 总: %d笔" % (len(wins), len(losses), len(wins)+len(losses)))
print("  胜率: %.2f%%" % (len(wins) / (len(wins)+len(losses)) * 100))
print("  平均盈利: +%d元" % avg_win)
print("  平均亏损: %d元" % (-avg_loss))
print("  盈亏比: %.2f:1" % (avg_win / avg_loss))
print("  盈利因子(PF): %.2f" % (total_win / total_loss))

year_trades = defaultdict(lambda: {"w": 0, "l": 0, "pnl": 0})
for t in trades:
    y = t["sell_date"][:4]
    pnl = float(t["net_pnl"])
    if pnl > 0:
        year_trades[y]["w"] += 1
    else:
        year_trades[y]["l"] += 1
    year_trades[y]["pnl"] += pnl

print()
print("年度交易明细:")
print("  年份   笔数  胜率    净盈亏       单笔均值")
for y in sorted(year_trades.keys()):
    d = year_trades[y]
    total = d["w"] + d["l"]
    wr = d["w"] / total * 100 if total else 0
    avg = d["pnl"] / total if total else 0
    print("  %s  %3d  %5.1f%%  %+10.0f  %+8.0f" % (y, total, wr, d["pnl"], avg))
