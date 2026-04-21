#!/usr/bin/env python3
"""检查亨通光电600487.SH在4/15-4/20的信号条件"""
import pandas as pd, numpy as np, pickle, sys
sys.path.insert(0, '.')
from quant.sim_replay_common import safe_num

p = 'data/cache/sim_replay_prepared/600487.SH_20230101_20260420.pkl'
with open(p, 'rb') as f:
    df = pickle.load(f)

for check_date in ['20260415', '20260416', '20260417', '20260420']:
    mask = df['trade_date'].astype(str) == check_date
    if not mask.any():
        print(f"{check_date}: not found")
        continue
    idx = df[mask].index[0]
    row = df.iloc[idx]
    
    print(f"\n=== {check_date} (idx={idx}) ===")
    print(f"  close={row['close']}, white={row['white_line']:.3f}, yellow={row['yellow_line']:.3f}")
    print(f"  high={row['high']}, white>=yellow? {row['white_line'] >= row['yellow_line']}")
    print(f"  high>=white? {row['high'] >= row['white_line']}")
    
    # 砖型图条件
    brick_raw = bool(row.get('brick_raw_turn_red', False))
    brick_hist = bool(row.get('brick_history_ok', False))
    print(f"  brick_raw_turn_red={brick_raw}, brick_history_ok={brick_hist}")
    
    if brick_raw and brick_hist and idx >= 4:
        z = safe_num(df["brick_formula_value"]).fillna(0)
        g = df["brick_formula_green"].fillna(False).astype(bool)
        g4 = g.iloc[idx-1] and g.iloc[idx-2] and g.iloc[idx-3] and g.iloc[idx-4]
        z_decrease = z.iloc[idx-4] > z.iloc[idx-3] > z.iloc[idx-2] > z.iloc[idx-1]
        z_turn = z.iloc[idx] >= z.iloc[idx-1]
        print(f"  green[-1,-2,-3,-4] = {g.iloc[idx-1]}, {g.iloc[idx-2]}, {g.iloc[idx-3]}, {g.iloc[idx-4]}")
        print(f"  Z values: [-4]={z.iloc[idx-4]:.2f}, [-3]={z.iloc[idx-3]:.2f}, [-2]={z.iloc[idx-2]:.2f}, [-1]={z.iloc[idx-1]:.2f}, [0]={z.iloc[idx]:.2f}")
        print(f"  green4={g4}, z_decrease={z_decrease}, z_turn={z_turn}")
        print(f"  BRICK OK = {g4 and z_decrease and z_turn}")
    else:
        print(f"  BRICK base fail: raw={brick_raw}, hist={brick_hist}")
    
    J = row.get('kdj_j', 999)
    print(f"  kdj_j={J:.2f}, J<=13? {J <= 13}")
    if J > 13:
        print(f"  B1: J值不满足 (need<=13, got {J:.2f})")
    else:
        print(f"  B1: J值满足，需完整检查")
