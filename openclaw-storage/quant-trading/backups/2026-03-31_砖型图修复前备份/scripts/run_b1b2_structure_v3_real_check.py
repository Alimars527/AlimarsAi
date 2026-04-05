import sys, json
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.batch_backtest import BatchBacktester
from quant.indicators import add_tactic_base_indicators
from quant.b1_perfect_features import add_b1_perfect_features
from quant.b1_b2_signals import detect_b1_b2_signals
from quant.single_pin_bucket import add_single_pin_low20_flags
from quant.brick_bucket import add_brick_flags
from quant.brick_formula import add_brick_formula_flags
from quant.tactic_router import route_tactic
from quant.b1b2_structure_features import add_b1b2_structure_features

START='20230101'
END='20260325'
OUT = project_root/'outputs'/'b1b2_structure_v3_real_check_2026-03-26.json'

runner = BatchBacktester(project_root)
universe = runner.filter_universe(runner.load_universe())
rows=[]
for _, r in universe.iterrows():
    code = r['ts_code']
    industry = r.get('industry','')
    df = runner.backtester._prepare_daily_frame(code, industry=industry)
    if df is None or df.empty or len(df) < 40:
        continue
    df = add_tactic_base_indicators(df)
    df = add_b1_perfect_features(df)
    df = detect_b1_b2_signals(df)
    df = add_single_pin_low20_flags(df)
    df = add_brick_flags(df)
    df = add_brick_formula_flags(df)
    df = add_b1b2_structure_features(df)
    df['trade_date'] = df['trade_date'].astype(str)
    df = df[(df['trade_date'] >= START) & (df['trade_date'] <= END)]
    for _, row in df.iterrows():
        item = {
            'trade_date': row['trade_date'],
            'code': code,
            'pct_chg': float(pd.to_numeric(row.get('pct_chg'), errors='coerce') or 0),
            'day_b1': bool(row.get('day_b1', False)),
            'week_b1': False,
            'perfect_b1': bool(row.get('perfect_b1', False)),
            'standard_b1': bool(row.get('standard_b1', False)),
            'weak_b1': bool(row.get('weak_b1', False)),
            'b1_strength': int(pd.to_numeric(row.get('b1_strength'), errors='coerce') if pd.notna(pd.to_numeric(row.get('b1_strength'), errors='coerce')) else 0),
            'b2_signal': bool(row.get('b2_signal', False)),
            'b2_strength': int(pd.to_numeric(row.get('b2_strength'), errors='coerce') if pd.notna(pd.to_numeric(row.get('b2_strength'), errors='coerce')) else 0),
            'single_pin_low20': bool(row.get('single_pin_low20', False)),
            'single_pin_four_zero': bool(row.get('single_pin_four_zero', False)),
            'single_pin_white_cross_red': bool(row.get('single_pin_white_cross_red', False)),
            'single_pin_white_cross_yellow': bool(row.get('single_pin_white_cross_yellow', False)),
            'brick_exec_ready': bool(row.get('brick_exec_ready', False)),
            'brick_red_turn': bool(row.get('brick_red_turn', False)),
            'brick_formula_signal': bool(row.get('brick_formula_signal', False)),
            'brick_formula_strong_signal': bool(row.get('brick_formula_strong_signal', False)),
            'reason': '',
            'strategy_tag': '技术备选',
            'trend_tier': '技术备选',
            'execution_style': '',
            'secondary_confirm_tier': '',
        }
        routed = route_tactic(item)
        if routed.get('hit_b2', False) and routed.get('hit_b1', False) and (not routed.get('hit_brick', False)) and pd.to_numeric(row.get('b1_strength'), errors='coerce') >= 5 and pd.to_numeric(row.get('b2_strength'), errors='coerce') == 4 and 4.7 <= pd.to_numeric(row.get('pct_chg'), errors='coerce') <= 5.8 and bool(row.get('b1b2_platform_restart', False)):
            rows.append({'trade_date': row['trade_date'], 'code': code})

sub = pd.DataFrame(rows).drop_duplicates().sort_values(['code','trade_date'])
sub['trade_date_dt'] = pd.to_datetime(sub['trade_date']) if not sub.empty else pd.Series(dtype='datetime64[ns]')
keep=[]; last={}
for idx, row in sub.iterrows():
    code=row['code']; td=row['trade_date_dt']
    if code not in last or (td-last[code]).days > 10:
        keep.append(idx); last[code]=td
sub = sub.loc[keep].copy()
daily = sub.groupby('trade_date').agg(symbol_count=('code','nunique')).reset_index().sort_values('trade_date') if not sub.empty else pd.DataFrame(columns=['trade_date','symbol_count'])
if not daily.empty:
    daily['trade_date'] = pd.to_datetime(daily['trade_date'])
    gaps = daily['trade_date'].diff().dropna().dt.days
    freq = {'event_count': int(len(sub)), 'signal_days': int(len(daily)), 'avg_symbols_per_signal_day': float(daily['symbol_count'].mean()), 'avg_gap_days': float(gaps.mean()) if not gaps.empty else None, 'median_gap_days': float(gaps.median()) if not gaps.empty else None}
else:
    freq = {'event_count':0,'signal_days':0,'avg_symbols_per_signal_day':None,'avg_gap_days':None,'median_gap_days':None}
res = {'name':'B1B2_STRUCTURE_V3_REAL','frequency':freq}
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(res, ensure_ascii=False, indent=2))
