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


if __name__ == '__main__':
    runner = BatchBacktester(project_root)
    universe = runner.filter_universe(runner.load_universe()).head(120)
    rows = []
    for _, r in universe.iterrows():
        code = r['ts_code']
        name = r.get('name', '')
        industry = r.get('industry', '')
        result = runner.backtester.run_single_code(code, strategy_name='主线趋势', hold_days=1, industry=industry)
        if result.get('status') != 'ok':
            continue
        style_counts = result.get('style_counts', {})
        dominant_style = dominant_style_from_counts(style_counts)
        trend_tier = normalize_trend_tier(dominant_style)
        if trend_tier != '主线趋势-优先' or industry not in ALLOWED_INDUSTRIES:
            continue

        # rebuild exit detail from sample_signals not enough; use backtester internals directly
        df = runner.backtester._prepare_daily_frame(code, industry=industry)
        if df.empty:
            continue
        signals = []
        for _, row in df.iterrows():
            res = runner.backtester.signal_engine.evaluate('主线趋势', row)
            if res['passed']:
                signals.append({
                    'trade_date': row['trade_date'],
                    'close': row['close'],
                    'pct_chg': row.get('pct_chg', 0),
                    'execution_style': '',
                    'trend_style': row.get('trend_style', ''),
                    'reason': res['reason'],
                })
        sig_df = pd.DataFrame(signals)
        if sig_df.empty:
            continue
        base_frame = df[['trade_date', 'open', 'high', 'low', 'close', 'pct_chg']].copy()
        exit_sim = runner.backtester.exit_backtester.simulate(
            sig_df,
            base_frame,
            strategy_tag='主线趋势',
            shares=runner.backtester.simulator.lot_size,
            simulator=runner.backtester.simulator,
            price_mode='low',
        )
        if exit_sim.empty:
            continue
        for exit_type, g in exit_sim.groupby('exit_type'):
            rows.append({
                'ts_code': code,
                'name': name,
                'industry': industry,
                'exit_type': exit_type,
                'count': int(len(g)),
                'avg_return': round(float(g['return_pct'].mean()), 4),
                'win_rate': round(float((g['return_pct'] > 0).mean()), 4),
            })

    out = pd.DataFrame(rows)
    summary = out.groupby(['industry', 'exit_type']).agg(
        sample_count=('count', 'sum'),
        avg_return=('avg_return', 'mean'),
        avg_win_rate=('win_rate', 'mean'),
    ).reset_index() if not out.empty else pd.DataFrame()
    print({'status': 'ok', 'summary': summary.to_dict(orient='records') if not summary.empty else []})
