"""第二阶段：回测主流程骨架（第一版）"""

from pathlib import Path
import yaml
import pandas as pd

from .signal_engine import SignalEngine
from .simulator import SimpleSimulator
from .metrics import summarize_returns


def load_backtest_config(project_root):
    config_path = Path(project_root) / 'config' / 'backtest.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class BacktestRunner:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.config = load_backtest_config(project_root)
        self.signal_engine = SignalEngine()
        exec_cfg = self.config.get('execution', {})
        self.simulator = SimpleSimulator(
            commission_rate=exec_cfg.get('commission_rate', 0.000086),
            min_commission=exec_cfg.get('min_commission', 5),
            stamp_tax_sell=exec_cfg.get('stamp_tax_sell', 0.0005),
            lot_size=exec_cfg.get('lot_size', 100),
        )

    def demo_run(self):
        sample = pd.DataFrame([
            {'trade_date': '20260317', 'close': 10.0, 'ma5': 9.8, 'ma10': 9.5, 'vol_ratio': 1.5, 'pct_chg': 2.0, 'benchmark_pct_chg': 0.5, 'distance_to_high': 0.04, 'preferred_industry': True},
            {'trade_date': '20260318', 'close': 10.3, 'ma5': 10.0, 'ma10': 9.6, 'vol_ratio': 1.3, 'pct_chg': 3.0, 'benchmark_pct_chg': 0.8, 'distance_to_high': 0.03, 'preferred_industry': True},
            {'trade_date': '20260319', 'close': 10.5, 'ma5': 10.2, 'ma10': 9.8, 'vol_ratio': 1.1, 'pct_chg': 1.5, 'benchmark_pct_chg': 0.1, 'distance_to_high': 0.02, 'preferred_industry': True},
            {'trade_date': '20260320', 'close': 10.1, 'ma5': 10.15, 'ma10': 9.9, 'vol_ratio': 0.9, 'pct_chg': -3.8, 'benchmark_pct_chg': -1.2, 'distance_to_high': 0.06, 'preferred_industry': True},
        ])
        signal = self.signal_engine.evaluate('主线趋势', sample.iloc[0])
        sim = self.simulator.simulate_hold_period(sample[['trade_date', 'close']], hold_days=1)
        metrics = summarize_returns(sim)
        return {
            'signal_demo': signal,
            'simulation_demo': sim.to_dict(orient='records'),
            'metrics_demo': metrics,
        }

    def run(self):
        return {
            'status': 'initialized',
            'message': '第二阶段回测骨架已初始化，已接入信号引擎/模拟器/指标模块的第一版演示。',
            'config': self.config,
            'demo': self.demo_run(),
        }
