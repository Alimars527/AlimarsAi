import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.local_backtest import LocalBacktester

TARGET_CODES = [
    '000727.SZ',  # 冠捷科技
    '000725.SZ',  # 京东方A
    '600601.SH',  # 方正科技
    '000509.SZ',  # 华塑控股
    '000670.SZ',  # 盈方微
    '002681.SZ',  # 奋达科技
]

if __name__ == '__main__':
    backtester = LocalBacktester(project_root)
    rows = []
    for code in TARGET_CODES:
        df = backtester._prepare_daily_frame(code, industry='元器件')
        if df.empty:
            continue
        rows.append({
            'ts_code': code,
            'avg_close': round(float(pd.to_numeric(df['close'], errors='coerce').dropna().mean()), 4),
            'avg_volatility_10': round(float(pd.to_numeric(df['volatility_10'], errors='coerce').dropna().mean()), 4),
            'avg_strong_days_10': round(float(pd.to_numeric(df['strong_days_10'], errors='coerce').dropna().mean()), 4),
            'avg_distance_to_high': round(float(pd.to_numeric(df['distance_to_high'], errors='coerce').dropna().mean()), 4),
            'avg_mf_positive_days_5': round(float(pd.to_numeric(df['mf_positive_days_5'], errors='coerce').dropna().mean()), 4),
            'avg_mf_strength': round(float(pd.to_numeric(df['mf_strength'], errors='coerce').dropna().mean()), 6),
            'latest_close': round(float(pd.to_numeric(df['close'], errors='coerce').dropna().iloc[-1]), 4),
            'latest_mf_positive_days_5': round(float(pd.to_numeric(df['mf_positive_days_5'], errors='coerce').dropna().iloc[-1]), 4),
            'latest_mf_strength': round(float(pd.to_numeric(df['mf_strength'], errors='coerce').dropna().iloc[-1]), 6),
        })
    out = pd.DataFrame(rows)
    summary = {
        'count': int(len(out)),
        'avg_close': round(float(out['avg_close'].mean()), 4) if not out.empty else None,
        'avg_volatility_10': round(float(out['avg_volatility_10'].mean()), 4) if not out.empty else None,
        'avg_strong_days_10': round(float(out['avg_strong_days_10'].mean()), 4) if not out.empty else None,
        'avg_distance_to_high': round(float(out['avg_distance_to_high'].mean()), 4) if not out.empty else None,
        'avg_mf_positive_days_5': round(float(out['avg_mf_positive_days_5'].mean()), 4) if not out.empty else None,
        'avg_mf_strength': round(float(out['avg_mf_strength'].mean()), 6) if not out.empty else None,
    }
    print({'status': 'ok', 'summary': summary, 'rows': out.to_dict(orient='records')})
