"""第二阶段：基于本地历史数据的第一版回测"""

from pathlib import Path
import pandas as pd

from .local_data_store import LocalDataStore
from .signal_engine import SignalEngine
from .simulator import SimpleSimulator
from .metrics import summarize_returns
from .backtest_runner import load_backtest_config
from .config import load_preferences
from .entry_backtest import EntryBacktester
from .scenario_entry_backtest import ScenarioEntryBacktester
from .exit_backtest import ExitBacktester
from .style_classifier import classify_trend_style
from .moneyflow_features import add_moneyflow_features
from .hkhold_features import add_hkhold_features
from .margin_features import add_margin_features


class LocalBacktester:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.config = load_backtest_config(project_root)
        self.preferences = load_preferences()
        self.store = LocalDataStore(self.project_root / 'data')
        self.signal_engine = SignalEngine()
        exec_cfg = self.config.get('execution', {})
        self.simulator = SimpleSimulator(
            commission_rate=exec_cfg.get('commission_rate', 0.000086),
            min_commission=exec_cfg.get('min_commission', 5),
            stamp_tax_sell=exec_cfg.get('stamp_tax_sell', 0.0005),
            lot_size=exec_cfg.get('lot_size', 100),
        )
        self.entry_backtester = EntryBacktester()
        self.scenario_entry_backtester = ScenarioEntryBacktester()
        self.exit_backtester = ExitBacktester()
        self.preferred_industries = set(self.preferences.get('candidate_filters', {}).get('prefer_industries', []))

    def _prepare_daily_frame(self, ts_code: str, industry: str = ''):
        daily = self.store.load('daily', ts_code)
        basic = self.store.load('daily_basic', ts_code)
        moneyflow_df = self.store.load('moneyflow', ts_code)
        hkhold_df = self.store.load('hkhold', ts_code)
        margin_detail_df = self.store.load('margin_detail', ts_code)
        index_df = self.store.load('index_daily', '000001.SH')
        if daily.empty or basic.empty:
            return pd.DataFrame()

        for col in ['close', 'pct_chg']:
            if col in daily.columns:
                daily[col] = pd.to_numeric(daily[col], errors='coerce')
        if 'volume_ratio' in basic.columns:
            basic['volume_ratio'] = pd.to_numeric(basic['volume_ratio'], errors='coerce')
        if not index_df.empty and 'pct_chg' in index_df.columns:
            index_df['pct_chg'] = pd.to_numeric(index_df['pct_chg'], errors='coerce')

        basic_cols = ['trade_date', 'volume_ratio'] if 'volume_ratio' in basic.columns else ['trade_date']
        df = daily.merge(basic[basic_cols], on='trade_date', how='left')
        if not index_df.empty:
            df = df.merge(index_df[['trade_date', 'pct_chg']].rename(columns={'pct_chg': 'benchmark_pct_chg'}), on='trade_date', how='left')
        else:
            df['benchmark_pct_chg'] = 0.0

        df = df.sort_values('trade_date').reset_index(drop=True)
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['recent_high_20'] = df['close'].rolling(20).max()
        df['distance_to_high'] = (df['recent_high_20'] - df['close']) / df['recent_high_20']
        df['return_1d'] = df['close'].pct_change()
        df['volatility_10'] = df['return_1d'].rolling(10).std()
        df['strong_day_flag'] = (df['pct_chg'] > df['benchmark_pct_chg']).astype(float) if 'benchmark_pct_chg' in df.columns else 0.0
        df['strong_days_10'] = df['strong_day_flag'].rolling(10).sum()
        df = add_moneyflow_features(df, moneyflow_df)
        df = add_hkhold_features(df, hkhold_df)
        df = add_margin_features(df, margin_detail_df)

        def regime(x):
            if pd.isna(x):
                return 'neutral'
            if x <= -1.0:
                return 'weak'
            if x >= 1.0:
                return 'strong'
            return 'neutral'

        df['market_regime'] = df['benchmark_pct_chg'].apply(regime)
        # 主线趋势默认优先平开/小低开承接：用当日收盘后的下一日开盘无法预知，
        # 第一版回测里先用“非极端波动日”做代理特征，后续再由场景回测进一步验证。
        df['prefer_flat_open'] = df['pct_chg'].abs() <= 6
        df['preferred_industry'] = industry in self.preferred_industries if industry else False
        df['industry'] = industry
        df = df.rename(columns={'volume_ratio': 'vol_ratio'})
        # 用过去滚动窗口近似“历史信号密度”，避免未来信息泄漏
        base_signal_proxy = (
            (df['close'] >= df['ma5']) &
            (df['ma5'] >= df['ma10']) &
            (df['pct_chg'] > df['benchmark_pct_chg'])
        ).astype(float)
        df['historical_signal_count'] = base_signal_proxy.rolling(120, min_periods=20).sum().fillna(0)
        df['trend_style'] = df.apply(lambda r: classify_trend_style(r), axis=1)
        return df

    def run_single_code(self, ts_code: str, strategy_name='主线趋势', hold_days=1, industry: str = ''):
        df = self._prepare_daily_frame(ts_code, industry=industry)
        if df.empty:
            return {'status': 'empty', 'code': ts_code}

        signals = []
        for _, row in df.iterrows():
            result = self.signal_engine.evaluate(strategy_name, row)
            if result['passed']:
                signals.append({
                    'trade_date': row['trade_date'],
                    'close': row['close'],
                    'pct_chg': row.get('pct_chg', 0),
                    'execution_style': '',
                    'trend_style': row.get('trend_style', ''),
                    'industry': industry,
                    'components_submodel': result.get('features', {}).get('components_submodel'),
                    'reason': result['reason'],
                })

        sig_df = pd.DataFrame(signals)
        if sig_df.empty:
            return {
                'status': 'ok',
                'code': ts_code,
                'signal_count': 0,
                'metrics': summarize_returns(pd.DataFrame()),
                'entry_metrics': summarize_returns(pd.DataFrame()),
            }

        merged = sig_df.merge(df[['trade_date', 'close']], on=['trade_date', 'close'], how='left')
        sim = self.simulator.simulate_hold_period(merged[['trade_date', 'close']], hold_days=hold_days)
        metrics = summarize_returns(sim)

        entry_results = {}
        scenario_summary = {}
        base_frame = df[['trade_date', 'open', 'high', 'low', 'close', 'pct_chg']].copy()
        for mode in ['low', 'mid', 'high']:
            entry_sim = self.entry_backtester.simulate_entry_trigger(
                sig_df,
                base_frame,
                hold_days=hold_days,
                strategy_tag=strategy_name,
                shares=self.simulator.lot_size,
                simulator=self.simulator,
                price_mode=mode,
            )
            entry_metrics = summarize_returns(entry_sim[entry_sim['triggered'] == True] if not entry_sim.empty and 'triggered' in entry_sim.columns else pd.DataFrame())
            trigger_rate = round(float(entry_sim['triggered'].mean()), 4) if not entry_sim.empty and 'triggered' in entry_sim.columns else None
            entry_results[mode] = {
                'trigger_rate': trigger_rate,
                'metrics': entry_metrics,
            }

        scenario_sim = self.scenario_entry_backtester.simulate(
            sig_df,
            base_frame,
            hold_days=hold_days,
            strategy_tag=strategy_name,
            shares=self.simulator.lot_size,
            simulator=self.simulator,
            price_mode='low',
        )
        if not scenario_sim.empty and 'scenario' in scenario_sim.columns:
            for scenario_name, group in scenario_sim[scenario_sim['triggered'] == True].groupby('scenario'):
                scenario_summary[scenario_name] = summarize_returns(group)

        exit_sim = self.exit_backtester.simulate(
            sig_df,
            base_frame,
            strategy_tag=strategy_name,
            shares=self.simulator.lot_size,
            simulator=self.simulator,
            price_mode='low',
        )
        exit_metrics = summarize_returns(exit_sim) if not exit_sim.empty else summarize_returns(pd.DataFrame())
        exit_scenario_summary = {}
        if not exit_sim.empty and 'open_scenario' in exit_sim.columns:
            for scenario_name, group in exit_sim.groupby('open_scenario'):
                exit_scenario_summary[scenario_name] = summarize_returns(group)

        style_counts = sig_df['trend_style'].value_counts().to_dict() if 'trend_style' in sig_df.columns else {}
        return {
            'status': 'ok',
            'code': ts_code,
            'signal_count': len(sig_df),
            'metrics': metrics,
            'entry_results': entry_results,
            'scenario_summary': scenario_summary,
            'exit_metrics': exit_metrics,
            'exit_scenario_summary': exit_scenario_summary,
            'style_counts': style_counts,
            'sample_signals': sig_df.tail(5).to_dict(orient='records'),
        }
