import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.batch_backtest import BatchBacktester

ALLOWED_INDUSTRIES = {'元器件', '电气设备', '软件服务'}


def analyze_signal_groups(sig_df: pd.DataFrame, sim_df: pd.DataFrame):
    if sig_df.empty or sim_df.empty:
        return {}
    join_col = 'trade_date'
    if 'buy_date' in sim_df.columns:
        sim_df = sim_df.rename(columns={'buy_date': 'trade_date'})
    merged = sig_df.merge(sim_df[['trade_date', 'return_pct']], on='trade_date', how='inner')
    if merged.empty:
        return {}

    def summary(sub):
        if sub.empty:
            return {'count': 0, 'avg_return': None, 'win_rate': None}
        return {
            'count': int(len(sub)),
            'avg_return': round(float(sub['return_pct'].mean()), 4),
            'win_rate': round(float((sub['return_pct'] > 0).mean()), 4),
        }

    out = {
        'mf_divergence_true': summary(merged[merged['mf_divergence'] == True]),
        'mf_divergence_false': summary(merged[merged['mf_divergence'] == False]),
        'mf_positive_5_true': summary(merged[merged['mf_positive_5'] == True]),
        'mf_positive_5_false': summary(merged[merged['mf_positive_5'] == False]),
        'mf_positive_days_5_ok_true': summary(merged[merged['mf_positive_days_5_ok'] == True]),
        'mf_positive_days_5_ok_false': summary(merged[merged['mf_positive_days_5_ok'] == False]),
    }
    return out


if __name__ == '__main__':
    runner = BatchBacktester(project_root)
    universe = runner.filter_universe(runner.load_universe())
    universe = universe[universe['industry'].isin(ALLOWED_INDUSTRIES)].head(120)
    rows = []
    industry_group_stats = []

    for _, r in universe.iterrows():
        code = r['ts_code']
        name = r.get('name', '')
        industry = r.get('industry', '')
        df = runner.backtester._prepare_daily_frame(code, industry=industry)
        if df.empty:
            continue
        signals = []
        for _, row in df.iterrows():
            # 这里改为“原始主线信号样本”口径：不加入 moneyflow 过滤，只保留基础趋势信号
            trend_up = bool(row.get('close', 0) >= row.get('ma5', 0) >= row.get('ma10', 0)) if row.get('ma5', 0) and row.get('ma10', 0) else False
            close_above_ma10 = bool(row.get('close', 0) >= row.get('ma10', 0)) if row.get('ma10', 0) else False
            strong_vs_market = bool(row.get('pct_chg', 0) > row.get('benchmark_pct_chg', 0))
            volume_up = bool((row.get('vol_ratio', 0) or 0) >= 1.5)
            below_recent_high = bool((row.get('distance_to_high', 999) or 999) <= 0.05)
            not_weak_market = bool(row.get('market_regime', 'neutral') != 'weak')
            prefer_flat_open = bool(row.get('prefer_flat_open', True))
            base_passed = all([
                trend_up,
                close_above_ma10,
                strong_vs_market,
                volume_up,
                below_recent_high,
                not_weak_market,
                prefer_flat_open,
            ])
            if base_passed:
                signals.append({
                    'trade_date': row['trade_date'],
                    'close': row['close'],
                    'mf_divergence': bool(row.get('mf_divergence', False)),
                    'mf_positive_5': float(row.get('mf_amount_5', 0) or 0) > 0,
                    'mf_positive_days_5_ok': float(row.get('mf_positive_days_5', 0) or 0) >= 3,
                })
        sig_df = pd.DataFrame(signals)
        if sig_df.empty:
            continue
        sim = runner.backtester.simulator.simulate_hold_period(sig_df[['trade_date', 'close']], hold_days=1)
        stats = analyze_signal_groups(sig_df, sim)
        rows.append({
            'ts_code': code,
            'name': name,
            'industry': industry,
            'signal_count': len(sig_df),
            'group_stats': stats,
        })

    for industry in sorted(ALLOWED_INDUSTRIES):
        industry_rows = [x for x in rows if x['industry'] == industry]
        if not industry_rows:
            continue
        def collect(group_name, field):
            vals = []
            counts = 0
            for item in industry_rows:
                stat = item['group_stats'].get(group_name, {})
                v = stat.get(field)
                c = stat.get('count', 0) or 0
                if v is not None and c > 0:
                    vals.append(v)
                    counts += c
            return (round(sum(vals) / len(vals), 4) if vals else None, counts)
        industry_group_stats.append({
            'industry': industry,
            'divergence_true_avg_return': collect('mf_divergence_true', 'avg_return')[0],
            'divergence_false_avg_return': collect('mf_divergence_false', 'avg_return')[0],
            'positive5_true_avg_return': collect('mf_positive_5_true', 'avg_return')[0],
            'positive5_false_avg_return': collect('mf_positive_5_false', 'avg_return')[0],
            'positive_days_ok_true_avg_return': collect('mf_positive_days_5_ok_true', 'avg_return')[0],
            'positive_days_ok_false_avg_return': collect('mf_positive_days_5_ok_false', 'avg_return')[0],
        })

    print({
        'status': 'ok',
        'sample_codes': len(rows),
        'industry_group_stats': industry_group_stats,
        'examples': rows[:10],
    })
