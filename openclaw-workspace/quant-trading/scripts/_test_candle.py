"""Quick smoke test for candlestick_patterns.py"""
import pandas as pd
from quant.candlestick_patterns import add_candlestick_patterns, ALL_PATTERN_COLS, GROUP_COLS

df = pd.read_csv("data/daily/000001.SZ.csv")
df = df.sort_values("trade_date").reset_index(drop=True)
df = add_candlestick_patterns(df)

print("Rows:", len(df))
print()

for col in ALL_PATTERN_COLS:
    cnt = int(df[col].sum())
    if cnt > 0:
        print("  %-30s = %d" % (col, cnt))

print()
for col in GROUP_COLS:
    cnt = int(df[col].sum())
    print("  %-30s = %d" % (col, cnt))

nan_counts = df[ALL_PATTERN_COLS + GROUP_COLS].isna().sum()
print("\nNaN check: %d total NaNs" % nan_counts.sum())

mask = df[ALL_PATTERN_COLS].any(axis=1)
hit = df[mask].tail(5)
print("\nLast 5 pattern hits:")
for _, row in hit.iterrows():
    pats = [p for p in ALL_PATTERN_COLS if row[p]]
    print("  %s close=%.2f => %s" % (row["trade_date"], row["close"], pats))
