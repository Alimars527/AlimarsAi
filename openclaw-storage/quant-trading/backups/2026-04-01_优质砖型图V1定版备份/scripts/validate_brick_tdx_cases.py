#!/usr/bin/env python3
import sys
from pathlib import Path
import pandas as pd

ROOT = Path('/Users/alimars/.openclaw/workspace/quant-trading')
sys.path.insert(0, str(ROOT))

from quant.local_backtest import LocalBacktester
from quant.indicators import add_tactic_base_indicators
from quant.b1_b2_signals import detect_b1_b2_signals
from quant.brick_formula import add_brick_formula_flags

CASES = {
    '000423.SZ': ('东阿阿胶', '中成药'),
    '600066.SH': ('宇通客车', '汽车整车'),
    '300166.SZ': ('东方国信', '软件服务'),
    '601006.SH': ('大秦铁路', '铁路'),
}
TRADE_DATE = '20260330'


def main():
    back = LocalBacktester(ROOT)
    rows = []
    for code, (name, industry) in CASES.items():
        df = back._prepare_daily_frame(code, industry=industry)
        if df is None or df.empty:
            rows.append({'code': code, 'name': name, 'status': 'empty'})
            continue
        df = add_tactic_base_indicators(df)
        df = detect_b1_b2_signals(df)
        df = add_brick_formula_flags(df)
        hit = df[df['trade_date'].astype(str) == TRADE_DATE]
        if hit.empty:
            rows.append({'code': code, 'name': name, 'status': 'missing_trade_date'})
            continue
        latest = hit.iloc[-1]
        prev = df[df['trade_date'].astype(str) < TRADE_DATE].iloc[-1]
        rows.append({
            'code': code,
            'name': name,
            'trade_date': TRADE_DATE,
            'history_len': int(len(df)),
            'brick_history_ok': bool(latest.get('brick_history_ok', False)),
            'prev_brick': float(latest.get('brick_formula_value', 0) if pd.isna(prev.get('brick_formula_value')) else prev.get('brick_formula_value')),
            'today_brick': float(latest.get('brick_formula_value', 0) or 0),
            'turn_red': bool(latest.get('brick_formula_turn_red', False)),
            'signal': bool(latest.get('brick_formula_signal', False)),
            'strong_signal': bool(latest.get('brick_formula_strong_signal', False)),
        })
    out = ROOT / 'outputs' / 'brick_tdx_validation_20260330.json'
    out.write_text(pd.DataFrame(rows).to_json(force_ascii=False, orient='records', indent=2), encoding='utf-8')
    print(out)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == '__main__':
    main()
