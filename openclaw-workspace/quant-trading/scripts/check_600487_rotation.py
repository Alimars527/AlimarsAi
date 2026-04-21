#!/usr/bin/env python3
"""检查600487亨通光电为什么没被选中 - rotation_ok, OMAV等"""
import pandas as pd, numpy as np, pickle, sys
from pathlib import Path
sys.path.insert(0, '.')
from quant.sim_replay_common import (
    build_prepared_universe, load_omav, load_trade_calendar, load_universe, safe_num
)

ROOT = Path('.')

# 加载OMAV
omav = load_omav(ROOT / 'data')
for td in ['20260415', '20260416', '20260417', '20260420']:
    row = omav[omav['trade_date'].astype(str) == td]
    if len(row) > 0:
        r = row.iloc[0]
        print(f"{td}: omav={r.get('omav','?')}, bear={r.get('omav_bear_regime_flag','?')}, warn={r.get('omav_rotation_warning_flag','?')}")
    else:
        print(f"{td}: no OMAV data")

# 加载meta看行业
meta = load_universe(ROOT / 'data')
m = meta[meta['ts_code'] == '600487.SH']
if len(m) > 0:
    print(f"\n600487.SH industry = {m.iloc[0]['industry']}")

# 加载rotation_map
print("\n加载prepared universe...")
meta2, code_data, code_idx, rotation_map = build_prepared_universe(
    '20230101', '20260420', ROOT / 'data', min_rows=40
)

# 检查rotation_map
code = '600487.SH'
r = meta2[meta2['ts_code'] == code]
if len(r) > 0:
    industry = r.iloc[0]['industry']
    print(f"600487 industry in meta: {industry}")
    for td in ['20260415', '20260416', '20260417', '20260420']:
        rok = rotation_map.get((td, industry), False)
        print(f"  {td} rotation_ok({industry}) = {rok}")

# 检查是否有信号被扫到
print("\n\n=== 模拟信号扫描 4/16 ===")
td = '20260416'
om = omav.set_index("trade_date").to_dict("index").get(td, {})
bear = str(om.get("omav_bear_regime_flag", "False")).lower() == "true"
warn = str(om.get("omav_rotation_warning_flag", "False")).lower() == "true"
max_new = 0 if bear else (1 if warn else 3)
print(f"OMAV: bear={bear}, warn={warn}, max_new={max_new}")

if code in code_idx and td in code_idx[code]:
    idx = code_idx[code][td]
    df = code_data[code]
    row = df.iloc[idx]
    next_row = df.iloc[idx + 1]
    
    brick_v1 = bool(row.get("brick_raw_turn_red", False)) and bool(row.get("brick_history_ok", False))
    print(f"brick_v1(raw+hist) = {brick_v1}")
    print(f"bear={bear}, warn={warn}")
    
    if brick_v1 and (not bear) and (not warn) and idx >= 4:
        z = safe_num(df["brick_formula_value"]).fillna(0)
        g = df["brick_formula_green"].fillna(False).astype(bool)
        white = safe_num(row.get("white_line"))
        yellow = safe_num(row.get("yellow_line"))
        high_b = safe_num(row.get("high"))
        r2 = meta2[meta2['ts_code'] == code]
        ind2 = r2.iloc[0]['industry'] if len(r2) > 0 else '???'
        rotation_ok = rotation_map.get((td, ind2), False)
        
        green4 = g.iloc[idx-1] and g.iloc[idx-2] and g.iloc[idx-3] and g.iloc[idx-4]
        z_dec = z.iloc[idx-4] > z.iloc[idx-3] > z.iloc[idx-2] > z.iloc[idx-1]
        z_turn = z.iloc[idx] >= z.iloc[idx-1]
        w_y = pd.notna(white) and pd.notna(yellow) and pd.notna(high_b)
        h_w = high_b >= white
        w_gt_y = white > yellow
        
        print(f"rotation_ok = {rotation_ok}")
        print(f"white={white:.3f}, yellow={yellow:.3f}, high={high_b:.3f}")
        print(f"white>=yellow? {white >= yellow}, high>=white? {high_b >= white}, white>yellow? {white > yellow}")
        print(f"green4={green4}, z_dec={z_dec}, z_turn={z_turn}")
        print(f"All nan check: {w_y}")
        
        brick = rotation_ok and w_y and h_w and w_gt_y and green4 and z_dec and z_turn
        print(f"\n>>> BRICK_V3 signal = {brick}")
        print(f">>> blocked by rotation_ok? {not rotation_ok}")
