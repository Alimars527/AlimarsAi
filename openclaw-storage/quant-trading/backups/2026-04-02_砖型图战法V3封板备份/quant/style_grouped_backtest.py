"""第二阶段：主线趋势内部票性分层回测（第一版）"""

from pathlib import Path
import pandas as pd

from .grouped_backtest import GroupedBacktester


class StyleGroupedBacktester:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.runner = GroupedBacktester(project_root)

    def run(self, industries, hold_days=1, per_group_limit=30):
        universe = self.runner.runner.filter_universe(self.runner.runner.load_universe())
        results = []
        for industry in industries:
            group = universe[universe['industry'] == industry].head(per_group_limit).copy()
            if group.empty:
                continue
            rows = []
            for _, r in group.iterrows():
                code = r['ts_code']
                name = r.get('name', '')
                result = self.runner.runner.backtester.run_single_code(
                    code,
                    strategy_name='主线趋势',
                    hold_days=hold_days,
                    industry=industry,
                )
                if result.get('status') != 'ok':
                    continue
                style_counts = result.get('style_counts', {})
                metric = result.get('metrics', {})
                rows.append({
                    'ts_code': code,
                    'name': name,
                    'industry': industry,
                    'avg_return': metric.get('avg_return'),
                    'win_rate': metric.get('win_rate'),
                    '高弹性主线': style_counts.get('高弹性主线', 0),
                    '稳定趋势主线': style_counts.get('稳定趋势主线', 0),
                    '边缘趋势': style_counts.get('边缘趋势', 0),
                })
            df = pd.DataFrame(rows)
            if df.empty:
                continue
            # 改为占比阈值判定，而不是简单次数最多
            def dominant_style(row):
                total = row['高弹性主线'] + row['稳定趋势主线'] + row['边缘趋势']
                if total <= 0:
                    return '边缘趋势'
                high_ratio = row['高弹性主线'] / total
                stable_ratio = row['稳定趋势主线'] / total
                if high_ratio >= 0.22:
                    return '高弹性主线'
                if stable_ratio >= 0.20:
                    return '稳定趋势主线'
                return '边缘趋势'
            df['dominant_style'] = df.apply(dominant_style, axis=1)
            summary = df.groupby('dominant_style').agg(
                sample_count=('ts_code', 'count'),
                avg_return=('avg_return', 'mean'),
                avg_win_rate=('win_rate', 'mean'),
            ).reset_index()
            results.append({
                'industry': industry,
                'style_summary': summary.to_dict(orient='records'),
                'top_codes': df.sort_values('avg_return', ascending=False).head(8).to_dict(orient='records'),
            })
        return {'status': 'ok', 'groups': results}
