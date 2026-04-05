import sys
from pathlib import Path
import pandas as pd
import tushare as ts

project_root = Path('/Users/alimars/.openclaw/workspace/quant-trading')
sys.path.insert(0, str(project_root))

from quant.local_backtest import LocalBacktester
from quant.indicators import add_tactic_base_indicators
from quant.b1_b2_signals import detect_b1_b2_signals
from quant.brick_formula import add_brick_formula_flags

TOKEN = 'be0e395aeb600a02110bcac4fca37a8d5b792afe8f13507040357d23'
ts.set_token(TOKEN)
pro = ts.pro_api()

CASES = {
    '000065.SZ': ('北方国际', '建筑工程'),
    '001203.SZ': ('大中矿业', '矿物制品'),
    '002756.SZ': ('永兴材料', '小金属'),
}


def append_trade_date(df, code):
    daily = pro.daily(ts_code=code, trade_date='20260323')
    if daily is None or daily.empty:
        return df
    daily = daily.copy()
    for c in ['open', 'high', 'low', 'close', 'vol', 'pct_chg']:
        if c in daily.columns:
            daily[c] = pd.to_numeric(daily[c], errors='coerce')
    row = {c: pd.NA for c in df.columns}
    for c in daily.columns:
        if c in row:
            row[c] = daily.iloc[0][c]
    row['trade_date'] = '20260323'
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


if __name__ == '__main__':
    back = LocalBacktester(project_root)
    for code, (name, industry) in CASES.items():
        df = back._prepare_daily_frame(code, industry=industry)
        if df is None or df.empty:
            print({'code': code, 'name': name, 'status': 'empty'})
            continue
        df = append_trade_date(df, code)
        df = add_tactic_base_indicators(df)
        df = detect_b1_b2_signals(df)
        df = add_brick_formula_flags(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        print({
            'code': code,
            'name': name,
            'trade_date': latest.get('trade_date'),
            'close': latest.get('close'),
            'pct_chg': latest.get('pct_chg'),
            'prev_brick': prev.get('brick_formula_value'),
            'today_brick': latest.get('brick_formula_value'),
            'turn_red': latest.get('brick_formula_turn_red'),
            'height_ok': latest.get('brick_formula_height_ok'),
            'volume_boost': latest.get('brick_formula_volume_boost'),
            'signal': latest.get('brick_formula_signal'),
            'strong_signal': latest.get('brick_formula_strong_signal'),
            'day_b1': latest.get('day_b1'),
            'standard_b1': latest.get('standard_b1'),
            'perfect_b1': latest.get('perfect_b1'),
        })
