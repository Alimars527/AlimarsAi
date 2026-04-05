import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.batch_backtest import BatchBacktester
from quant.trend_tier_map import normalize_trend_tier

ALLOWED_INDUSTRIES = {'元器件', '电气设备', '软件服务'}


def dominant_style_from_counts(style_counts):
    high = style_counts.get('高弹性主线', 0)
    stable = style_counts.get('稳定趋势主线', 0)
    edge = style_counts.get('边缘趋势', 0)
    total = high + stable + edge
    if total <= 0:
        return '边缘趋势'
    high_ratio = high / total
    stable_ratio = stable / total
    if high_ratio >= 0.22:
        return '高弹性主线'
    if stable_ratio >= 0.20:
        return '稳定趋势主线'
    return '边缘趋势'


def summarize_window(start_date: str):
    runner = BatchBacktester(project_root)
    universe = runner.filter_universe(runner.load_universe()).head(120)
    rows = []
    for _, r in universe.iterrows():
        code = r['ts_code']
        name = r.get('name', '')
        industry = r.get('industry', '')

        df = runner.backtester._prepare_daily_frame(code, industry=industry)
        if df.empty:
            continue
        df = df[df['trade_date'] >= start_date].copy()
        if df.empty:
            continue

        signals = []
        for _, row in df.iterrows():
            result = runner.backtester.signal_engine.evaluate('主线趋势', row)
            if result['passed']:
                signals.append({
                    'trade_date': row['trade_date'],
                    'close': row['close'],
                    'pct_chg': row.get('pct_chg', 0),
                    'execution_style': '',
                    'trend_style': row.get('trend_style', ''),
                    'reason': result['reason'],
                })
        sig_df = pd.DataFrame(signals)
        if sig_df.empty:
            continue

        merged = sig_df.merge(df[['trade_date', 'close']], on=['trade_date', 'close'], how='left')
        sim = runner.backtester.simulator.simulate_hold_period(merged[['trade_date', 'close']], hold_days=1)
        metric = runner.backtester.exit_backtester.simulate(
            sig_df,
            df[['trade_date', 'open', 'high', 'low', 'close', 'pct_chg']].copy(),
            strategy_tag='主线趋势',
            shares=runner.backtester.simulator.lot_size,
            simulator=runner.backtester.simulator,
            price_mode='low',
        )
        base_metrics = runner.backtester.exit_backtester.simulate(
            sig_df,
            df[['trade_date', 'open', 'high', 'low', 'close', 'pct_chg']].copy(),
            strategy_tag='主线趋势',
            shares=runner.backtester.simulator.lot_size,
            simulator=runner.backtester.simulator,
            price_mode='low',
        )
        style_counts = sig_df['trend_style'].value_counts().to_dict() if 'trend_style' in sig_df.columns else {}
        dominant_style = dominant_style_from_counts(style_counts)
        trend_tier = normalize_trend_tier(dominant_style)
        if trend_tier != '主线趋势-优先' or industry not in ALLOWED_INDUSTRIES:
            continue
        rows.append({
            'ts_code': code,
            'name': name,
            'industry': industry,
            'signal_count': len(sig_df),
            'avg_return': sim['return_pct'].mean() if not sim.empty and 'return_pct' in sim.columns else None,
            'win_rate': (sim['return_pct'] > 0).mean() if not sim.empty and 'return_pct' in sim.columns else None,
            'exit_avg_return': base_metrics['return_pct'].mean() if not base_metrics.empty and 'return_pct' in base_metrics.columns else None,
            'exit_win_rate': (base_metrics['return_pct'] > 0).mean() if not base_metrics.empty and 'return_pct' in base_metrics.columns else None,
            'trend_tier': trend_tier,
        })
    result_df = pd.DataFrame(rows)
    if result_df.empty:
        return {'window_start': start_date, 'status': 'empty'}
    return {
        'window_start': start_date,
        'sample_count': int(len(result_df)),
        'avg_return': round(float(result_df['avg_return'].dropna().mean()), 4),
        'avg_win_rate': round(float(result_df['win_rate'].dropna().mean()), 4),
        'avg_exit_return': round(float(result_df['exit_avg_return'].dropna().mean()), 4),
        'avg_exit_win_rate': round(float(result_df['exit_win_rate'].dropna().mean()), 4),
        'top': result_df.sort_values('avg_return', ascending=False).head(10).to_dict(orient='records'),
    }


if __name__ == '__main__':
    print({
        'compare': [
            summarize_window('20240101'),
            summarize_window('20230101'),
        ]
    })
