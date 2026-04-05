"""第二阶段：批量样本回测（第一版）"""

from pathlib import Path
import pandas as pd

from .local_backtest import LocalBacktester


class BatchBacktester:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.backtester = LocalBacktester(project_root)
        self.stock_basic_path = self.project_root / 'data' / 'meta' / 'stock_basic.csv'

    def load_universe(self):
        if not self.stock_basic_path.exists():
            return pd.DataFrame()
        df = pd.read_csv(self.stock_basic_path, dtype=str)
        return df

    def filter_universe(self, df: pd.DataFrame):
        if df.empty:
            return df
        df = df.copy()
        # 当前明确规则过滤：北交所/创业板/房地产相关/ST类
        if 'ts_code' in df.columns:
            df = df[~df['ts_code'].str.endswith('.BJ', na=False)]
        if 'market' in df.columns:
            df = df[df['market'] != '创业板']
        if 'industry' in df.columns:
            avoid = {'区域地产', '全国地产', '房产服务', '园区开发', '其他商业'}
            df = df[~df['industry'].isin(avoid)]
        if 'name' in df.columns:
            df = df[~df['name'].str.contains('ST', na=False)]
            df = df[~df['name'].str.contains('\*ST', na=False)]
        return df.reset_index(drop=True)

    def run_sample(self, strategy_name='主线趋势', hold_days=1, sample_size=100):
        universe = self.filter_universe(self.load_universe())
        if universe.empty:
            return {'status': 'empty_universe'}

        sample = universe.head(sample_size)
        rows = []
        for _, r in sample.iterrows():
            code = r['ts_code']
            name = r.get('name', '')
            industry = r.get('industry', '')
            result = self.backtester.run_single_code(code, strategy_name=strategy_name, hold_days=hold_days, industry=industry)
            if result.get('status') != 'ok':
                continue
            metric = result.get('metrics', {})
            entry_results = result.get('entry_results', {})
            low_res = entry_results.get('low', {}).get('metrics', {})
            mid_res = entry_results.get('mid', {}).get('metrics', {})
            high_res = entry_results.get('high', {}).get('metrics', {})
            scenarios = result.get('scenario_summary', {})
            exit_metrics = result.get('exit_metrics', {})
            exit_scenarios = result.get('exit_scenario_summary', {})
            rows.append({
                'ts_code': code,
                'name': name,
                'industry': industry,
                'signal_count': result.get('signal_count', 0),
                'count': metric.get('count'),
                'win_rate': metric.get('win_rate'),
                'avg_return': metric.get('avg_return'),
                'avg_win': metric.get('avg_win'),
                'avg_loss': metric.get('avg_loss'),
                'entry_trigger_rate_low': entry_results.get('low', {}).get('trigger_rate'),
                'entry_trigger_rate_mid': entry_results.get('mid', {}).get('trigger_rate'),
                'entry_trigger_rate_high': entry_results.get('high', {}).get('trigger_rate'),
                'entry_win_rate_low': low_res.get('win_rate'),
                'entry_win_rate_mid': mid_res.get('win_rate'),
                'entry_win_rate_high': high_res.get('win_rate'),
                'entry_avg_return_low': low_res.get('avg_return'),
                'entry_avg_return_mid': mid_res.get('avg_return'),
                'entry_avg_return_high': high_res.get('avg_return'),
                'flat_open_avg_return': scenarios.get('flat_open', {}).get('avg_return'),
                'high_open_avg_return': scenarios.get('high_open', {}).get('avg_return'),
                'low_open_avg_return': scenarios.get('low_open', {}).get('avg_return'),
                'exit_win_rate': exit_metrics.get('win_rate'),
                'exit_avg_return': exit_metrics.get('avg_return'),
                'exit_flat_open_return': exit_scenarios.get('flat_open', {}).get('avg_return'),
                'exit_high_open_return': exit_scenarios.get('high_open', {}).get('avg_return'),
                'exit_low_open_return': exit_scenarios.get('low_open', {}).get('avg_return'),
            })
        result_df = pd.DataFrame(rows)
        if result_df.empty:
            return {'status': 'no_result'}

        summary = {
            'sample_size': len(sample),
            'result_count': len(result_df),
            'avg_win_rate': round(float(result_df['win_rate'].dropna().mean()), 4) if 'win_rate' in result_df.columns else None,
            'avg_return': round(float(result_df['avg_return'].dropna().mean()), 4) if 'avg_return' in result_df.columns else None,
            'avg_entry_trigger_rate_low': round(float(result_df['entry_trigger_rate_low'].dropna().mean()), 4) if 'entry_trigger_rate_low' in result_df.columns else None,
            'avg_entry_trigger_rate_mid': round(float(result_df['entry_trigger_rate_mid'].dropna().mean()), 4) if 'entry_trigger_rate_mid' in result_df.columns else None,
            'avg_entry_trigger_rate_high': round(float(result_df['entry_trigger_rate_high'].dropna().mean()), 4) if 'entry_trigger_rate_high' in result_df.columns else None,
            'avg_entry_win_rate_low': round(float(result_df['entry_win_rate_low'].dropna().mean()), 4) if 'entry_win_rate_low' in result_df.columns else None,
            'avg_entry_win_rate_mid': round(float(result_df['entry_win_rate_mid'].dropna().mean()), 4) if 'entry_win_rate_mid' in result_df.columns else None,
            'avg_entry_win_rate_high': round(float(result_df['entry_win_rate_high'].dropna().mean()), 4) if 'entry_win_rate_high' in result_df.columns else None,
            'avg_entry_return_low': round(float(result_df['entry_avg_return_low'].dropna().mean()), 4) if 'entry_avg_return_low' in result_df.columns else None,
            'avg_entry_return_mid': round(float(result_df['entry_avg_return_mid'].dropna().mean()), 4) if 'entry_avg_return_mid' in result_df.columns else None,
            'avg_entry_return_high': round(float(result_df['entry_avg_return_high'].dropna().mean()), 4) if 'entry_avg_return_high' in result_df.columns else None,
            'avg_flat_open_return': round(float(result_df['flat_open_avg_return'].dropna().mean()), 4) if 'flat_open_avg_return' in result_df.columns else None,
            'avg_high_open_return': round(float(result_df['high_open_avg_return'].dropna().mean()), 4) if 'high_open_avg_return' in result_df.columns else None,
            'avg_low_open_return': round(float(result_df['low_open_avg_return'].dropna().mean()), 4) if 'low_open_avg_return' in result_df.columns else None,
            'avg_exit_win_rate': round(float(result_df['exit_win_rate'].dropna().mean()), 4) if 'exit_win_rate' in result_df.columns else None,
            'avg_exit_return': round(float(result_df['exit_avg_return'].dropna().mean()), 4) if 'exit_avg_return' in result_df.columns else None,
            'avg_exit_flat_open_return': round(float(result_df['exit_flat_open_return'].dropna().mean()), 4) if 'exit_flat_open_return' in result_df.columns else None,
            'avg_exit_high_open_return': round(float(result_df['exit_high_open_return'].dropna().mean()), 4) if 'exit_high_open_return' in result_df.columns else None,
            'avg_exit_low_open_return': round(float(result_df['exit_low_open_return'].dropna().mean()), 4) if 'exit_low_open_return' in result_df.columns else None,
        }
        return {
            'status': 'ok',
            'summary': summary,
            'top_by_return': result_df.sort_values('avg_return', ascending=False).head(10).to_dict(orient='records'),
            'bottom_by_return': result_df.sort_values('avg_return', ascending=True).head(10).to_dict(orient='records'),
        }
