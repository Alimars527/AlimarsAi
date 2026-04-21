#!/usr/bin/env python3
"""检查600487亨通光电的B1信号"""
import pandas as pd, numpy as np, pickle, sys
from pathlib import Path
sys.path.insert(0, '.')
from quant.sim_replay_common import build_prepared_universe, safe_num

ROOT = Path('.')
meta, code_data, code_idx, rotation_map = build_prepared_universe(
    '20230101', '20260420', ROOT / 'data', min_rows=40
)

code = '600487.SH'
df = code_data[code]

# 复制B1检查逻辑
def _sma_cn(series, n, m):
    x = safe_num(series).fillna(0.0)
    out = []
    prev = None
    for v in x.tolist():
        if prev is None:
            prev = v
        else:
            prev = (m * v + (n - m) * prev) / n
        out.append(prev)
    return pd.Series(out, index=series.index)

def b1_check_detail(df, idx):
    sub = df.iloc[: idx + 1].copy().reset_index(drop=True)
    if len(sub) < 160:
        return False, "len<160"
    C = safe_num(sub['close'])
    O = safe_num(sub['open'])
    H = safe_num(sub['high'])
    L = safe_num(sub['low'])
    VOL = safe_num(sub['vol']).fillna(0.0)
    REAL_YANG = (C > O) & ~(C < C.shift(1))
    REAL_YIN = (C < O) & ~(C > C.shift(1))
    ll9 = L.rolling(9).min(); hh9 = H.rolling(9).max()
    RSV = (C - ll9) / (hh9 - ll9) * 100
    K = _sma_cn(RSV, 3, 1)
    D = _sma_cn(K, 3, 1)
    J = 3 * K - 2 * D
    J_OK = J.iloc[-1] <= 13
    
    VOL_YANG1 = (VOL * REAL_YANG.astype(int)).rolling(57).sum().iloc[-1]
    VOL_YIN1 = (VOL * REAL_YIN.astype(int)).rolling(57).sum().iloc[-1]
    VOL_YANG2 = (VOL * REAL_YANG.astype(int)).rolling(14).sum().iloc[-1]
    VOL_YIN2 = (VOL * REAL_YIN.astype(int)).rolling(14).sum().iloc[-1]
    YANGYIN_OK1 = VOL_YANG1 > 1.25 * VOL_YIN1
    YANGYIN_OK2 = VOL_YANG2 > 2.25 * VOL_YIN2
    
    MV = safe_num(sub.get('total_mv_billion'))
    MVOK = MV.iloc[-1] >= 50
    
    O85 = O.rolling(21).min() + 0.95 * (O.rolling(21).max() - O.rolling(21).min())
    TOP15O = O.iloc[-1] >= O85.iloc[-1]
    FD15 = (C < C.shift(1)) & (C <= O) & (VOL >= 1.2 * VOL.shift(1))
    CNT28 = ((TOP15O & FD15).astype(int)).rolling(21).sum().iloc[-1]
    GOOD28 = CNT28 <= 0
    
    AVG40 = VOL.rolling(40).mean().iloc[-1]
    PLRY = (VOL > 1.95 * VOL.shift(1)) & (C > O) & (VOL > AVG40)
    PLRY_CNT_val = ((PLRY.astype(int)).rolling(14).sum() >= 2).iloc[-1] or ((PLRY.astype(int)).rolling(57).sum() >= 4).iloc[-1]
    
    prev_plry = PLRY.shift(1).eq(True)
    PLRY_FIRST = PLRY & (~prev_plry)
    PLRY_CONT = PLRY & prev_plry
    prev_real_yin = REAL_YIN.shift(1).eq(True)
    PRE_NOT_REALYIN = ~prev_real_yin
    HALF_DOWN = PRE_NOT_REALYIN & (C < C.shift(1)) & (VOL <= 0.5 * VOL.shift(1))
    CNT_FIRST = PLRY_FIRST.astype(int).rolling(57).sum().iloc[-1]
    CNT_CONT = PLRY_CONT.astype(int).rolling(57).sum().iloc[-1]
    CNT_HALF = HALF_DOWN.astype(int).rolling(57).sum().iloc[-1]
    THREE_SUM_OK = (CNT_FIRST + CNT_CONT + CNT_HALF) >= 4
    
    MAXVOL28 = VOL.rolling(28).max()
    MAX28_BAD = (VOL == MAXVOL28) & REAL_YIN
    MAX28_OK = MAX28_BAD.astype(int).rolling(28).sum().iloc[-1] == 0
    
    A1_cond1 = PLRY_CNT_val and YANGYIN_OK1 and J_OK and MVOK and GOOD28 and THREE_SUM_OK and MAX28_OK
    A1_cond2 = PLRY_CNT_val and YANGYIN_OK2 and J_OK and MVOK and GOOD28 and MAX28_OK
    A1 = A1_cond1 or A1_cond2
    
    wl = sub['white_line'].iloc[-1]
    yl = sub['yellow_line'].iloc[-1]
    B1 = (wl >= yl * 0.985) and (C.iloc[-1] >= yl * 0.985) and A1
    
    details = {
        'J': J.iloc[-1], 'J_OK': J_OK,
        'YANGYIN_OK1': YANGYIN_OK1, 'YANGYIN_OK2': YANGYIN_OK2,
        'MV': MV.iloc[-1] if pd.notna(MV.iloc[-1]) else 'NaN', 'MVOK': MVOK,
        'GOOD28': GOOD28, 'PLRY_CNT': PLRY_CNT_val,
        'THREE_SUM_OK': THREE_SUM_OK, 'MAX28_OK': MAX28_OK,
        'A1_cond1': A1_cond1, 'A1_cond2': A1_cond2, 'A1': A1,
        'wl': wl, 'yl': yl, 'wl>=yl*0.985': wl >= yl * 0.985,
        'close': C.iloc[-1], 'close>=yl*0.985': C.iloc[-1] >= yl * 0.985,
        'B1': B1,
    }
    return B1, details

for td in ['20260415', '20260416', '20260417', '20260420']:
    idx_map = code_idx[code]
    if td not in idx_map:
        print(f"{td}: not in idx_map")
        continue
    idx = idx_map[td]
    ok, det = b1_check_detail(df, idx)
    print(f"\n=== {td} B1 check ===")
    print(f"  B1 = {ok}")
    for k, v in det.items():
        if k != 'B1':
            print(f"  {k} = {v}")
