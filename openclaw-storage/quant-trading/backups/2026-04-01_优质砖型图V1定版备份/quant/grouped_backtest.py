"""第二阶段：分组复核（按行业/票型）"""

from pathlib import Path
import pandas as pd

from .batch_backtest import BatchBacktester


class GroupedBacktester:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.runner = BatchBacktester(project_root)

    def run_by_industries(self, industries, strategy_name='主线趋势', hold_days=1, per_group_limit=40):
        universe = self.runner.filter_universe(self.runner.load_universe())
        if universe.empty:
            return {'status': 'empty_universe'}

        results = []
        for industry in industries:
            group = universe[universe['industry'] == industry].head(per_group_limit).copy()
            if group.empty:
                continue
            rows = []
            for _, r in group.iterrows():
                code = r['ts_code']
                name = r.get('name', '')
                result = self.runner.backtester.run_single_code(
                    code,
                    strategy_name=strategy_name,
                    hold_days=hold_days,
                    industry=industry,
                )
                if result.get('status') != 'ok':
                    continue
                metric = result.get('metrics', {})
                exit_metric = result.get('exit_metrics', {})
                rows.append({
                    'ts_code': code,
                    'name': name,
                    'industry': industry,
                    'signal_count': result.get('signal_count', 0),
                    'avg_return': metric.get('avg_return'),
                    'win_rate': metric.get('win_rate'),
                    'exit_avg_return': exit_metric.get('avg_return'),
                    'exit_win_rate': exit_metric.get('win_rate'),
                })
            group_df = pd.DataFrame(rows)
            if group_df.empty:
                continue
            results.append({
                'industry': industry,
                'sample_count': len(group_df),
                'avg_return': round(float(group_df['avg_return'].dropna().mean()), 4),
                'avg_win_rate': round(float(group_df['win_rate'].dropna().mean()), 4),
                'avg_exit_return': round(float(group_df['exit_avg_return'].dropna().mean()), 4),
                'avg_exit_win_rate': round(float(group_df['exit_win_rate'].dropna().mean()), 4),
                'top_codes': group_df.sort_values('avg_return', ascending=False).head(5).to_dict(orient='records'),
            })
        return {
            'status': 'ok',
            'groups': results,
        }
