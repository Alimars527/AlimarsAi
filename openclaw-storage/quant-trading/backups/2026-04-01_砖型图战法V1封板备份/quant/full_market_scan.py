from pathlib import Path
import pandas as pd

from .data_loader import TushareClient
from .indicators import add_ma_features, add_tactic_base_indicators
from .config import load_preferences
from .style_classifier import classify_trend_style
from .moneyflow_features import add_moneyflow_features
from .hkhold_features import add_hkhold_features
from .margin_features import add_margin_features
from .b1_b2_signals import detect_b1_b2_signals
from .weekly_signals import detect_week_b1
from .b1_perfect_features import add_b1_perfect_features
from .single_pin_bucket import add_single_pin_low20_flags
from .brick_bucket import add_brick_flags
from .brick_formula import add_brick_formula_flags
from .local_data_store import LocalDataStore


class FullMarketScanner:
    def __init__(self):
        self.client = TushareClient()
        self.preferences = load_preferences().get('candidate_filters', {})
        self.project_root = Path(__file__).resolve().parent.parent
        self.store = LocalDataStore(self.project_root / 'data')

    def _load_stock_basic(self):
        p = self.project_root / 'data' / 'meta' / 'stock_basic.csv'
        if p.exists():
            return pd.read_csv(p, dtype=str)
        return self.client.fetch_stock_basic()

    def _load_local_daily(self, code: str, start_date: str, end_date: str):
        df = self.store.load('daily', code)
        if df.empty:
            return self.client.fetch_stock_daily(code, start_date, end_date)
        df = df[(df['trade_date'].astype(str) >= start_date) & (df['trade_date'].astype(str) <= end_date)].copy()
        return df.sort_values('trade_date').reset_index(drop=True)

    def _load_local_daily_basic(self, code: str, start_date: str, end_date: str):
        df = self.store.load('daily_basic', code)
        if df.empty:
            return pd.DataFrame()
        df = df[(df['trade_date'].astype(str) >= start_date) & (df['trade_date'].astype(str) <= end_date)].copy()
        return df.sort_values('trade_date').reset_index(drop=True)

    def _load_local_moneyflow(self, code: str):
        return self.store.load('moneyflow', code)

    def _load_local_hkhold(self, code: str):
        return self.store.load('hkhold', code)

    def _load_local_margin_detail(self, code: str):
        return self.store.load('margin_detail', code)

    def scan(self, trade_date: str, top_n: int = 10):
        stock_basic = self._load_stock_basic()
        if stock_basic.empty:
            return []
        results = []
        universe = stock_basic.head(300)
        if self.preferences.get('exclude_st', True):
            universe = universe[~universe['name'].astype(str).str.upper().str.contains('ST', na=False)]
        avoid_industries = set(self.preferences.get('avoid_industries', []))
        if avoid_industries:
            universe = universe[~universe['industry'].isin(avoid_industries)]
        min_price = float(self.preferences.get('min_price', 0))
        max_price = float(self.preferences.get('max_price', 99999))
        preferred = set(self.preferences.get('prefer_industries', []))
        preference_mode = self.preferences.get('preference_mode', 'weak_reference')
        resonance_whitelist = {'证券', '银行', '化工原料', '专用机械', '医疗保健'}

        for _, row in universe.iterrows():
            code = row['ts_code']
            df = self._load_local_daily(code, '20000101', trade_date)
            if df.empty or len(df) < 15:
                continue

            # 砖型图必须用全历史递归计算，避免窗口截短导致与通达信不一致
            full_daily = self.store.load('daily', code)
            if not full_daily.empty:
                full_daily = full_daily.sort_values('trade_date').reset_index(drop=True)
                for col in ['open', 'high', 'low', 'close', 'vol', 'pct_chg']:
                    if col in full_daily.columns:
                        full_daily[col] = pd.to_numeric(full_daily[col], errors='coerce')
                full_brick = add_brick_formula_flags(full_daily)
                brick_cols = [c for c in full_brick.columns if c.startswith('brick_')]
                brick_cols = ['trade_date'] + brick_cols
                df = df.merge(full_brick[brick_cols], on='trade_date', how='left')

            basic_df = self._load_local_daily_basic(code, '20000101', trade_date)
            if not basic_df.empty and 'volume_ratio' in basic_df.columns:
                basic_df['volume_ratio'] = pd.to_numeric(basic_df['volume_ratio'], errors='coerce')
                df = df.merge(basic_df[['trade_date', 'volume_ratio']], on='trade_date', how='left')
            for col in ['open', 'high', 'low', 'close', 'vol', 'pct_chg']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            df = add_ma_features(df)
            df = add_tactic_base_indicators(df)
            df['ma5'] = df['close'].rolling(5).mean()
            df['ma10'] = df['close'].rolling(10).mean()
            df['recent_high_20'] = df['close'].rolling(20).max()
            df['distance_to_high'] = (df['recent_high_20'] - df['close']) / df['recent_high_20']
            df['return_1d'] = df['close'].pct_change()
            df['volatility_10'] = df['return_1d'].rolling(10).std()
            df['strong_day_flag'] = (df['pct_chg'] > 0).astype(float)
            df['strong_days_10'] = df['strong_day_flag'].rolling(10).sum()
            if 'vol_ratio' not in df.columns:
                if 'volume_ratio' in df.columns:
                    df['vol_ratio'] = df['volume_ratio']
                else:
                    df['vol_ratio'] = (df['vol'] / df['vol'].rolling(5).mean()).fillna(0)

            moneyflow_df = self._load_local_moneyflow(code)
            if not moneyflow_df.empty:
                df = add_moneyflow_features(df, moneyflow_df)
            hkhold_df = self._load_local_hkhold(code)
            if not hkhold_df.empty:
                df = add_hkhold_features(df, hkhold_df)
            margin_detail_df = self._load_local_margin_detail(code)
            if not margin_detail_df.empty:
                df = add_margin_features(df, margin_detail_df)

            df = detect_b1_b2_signals(df)
            df = add_single_pin_low20_flags(df)
            df = add_brick_flags(df)
            if 'brick_formula_signal' not in df.columns:
                df = add_brick_formula_flags(df)
            weekly_df = detect_week_b1(df)
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            latest_week_b1 = bool(weekly_df.iloc[-1].get('week_b1', False)) if not weekly_df.empty else False

            if latest['close'] < min_price or latest['close'] > max_price:
                continue

            score = 0
            tags = []
            if row.get('industry', '') in preferred and preference_mode != 'none':
                score += 0.5
                tags.append('行业弱参考')
            if latest['close'] > latest['ma5'] > latest['ma10']:
                score += 2
                tags.append('短趋势向上')
            if latest['pct_chg'] > 2:
                score += 1
                tags.append('强于市场')
            if latest['vol'] > prev['vol']:
                score += 1
                tags.append('放量')
            if latest['close'] >= df.tail(15)['close'].max() * 0.97:
                score += 1
                tags.append('接近阶段高位')
            if float(latest.get('mf_amount_5', 0) or 0) > 0:
                score += 1
                tags.append('近5日资金净流入')
            if bool(latest.get('mf_divergence', False)):
                score -= 1
                tags.append('上涨资金背离')
            if bool(latest.get('single_pin_low20', False)):
                tags.append('单针')
            if bool(latest.get('brick_formula_signal', False)) or bool(latest.get('brick_formula_strong_signal', False)) or bool(latest.get('brick_exec_ready', False)):
                tags.append('砖型图')
                score += 1.5
            if bool(latest.get('brick_formula_strong_signal', False)):
                tags.append('砖型图放量强化')
                score += 1

            trend_style = classify_trend_style(latest)
            rotation_support = bool(latest.get('rotation_support', False))
            rotation_support_level = latest.get('rotation_support_level', 'none')
            if rotation_support:
                score += 1.5
                tags.append('轮动支持')
            if rotation_support_level == 'strong':
                score += 1.0
                tags.append('轮动强支持')
            if score >= 3:
                results.append({
                    'code': code,
                    'name': row['name'],
                    'industry': row.get('industry', ''),
                    'close': round(float(latest['close']), 2),
                    'pct_chg': round(float(latest['pct_chg']), 2),
                    'score': score,
                    'trend_style': trend_style,
                    'mf_divergence': bool(latest.get('mf_divergence', False)),
                    'mf_positive_5': bool(float(latest.get('mf_amount_5', 0) or 0) > 0),
                    'mf_positive_days_5_ok': bool(float(latest.get('mf_positive_days_5', 0) or 0) >= 3),
                    'hkhold_ratio': float(latest.get('hkhold_ratio', 0) or 0),
                    'hkhold_ratio_change': float(latest.get('hkhold_ratio_change', 0) or 0),
                    'hkhold_positive_5': float(latest.get('hkhold_ratio_positive_5', 0) or 0),
                    'day_b1': bool(latest.get('day_b1', False)),
                    'week_b1': latest_week_b1,
                    'b2_signal': bool(latest.get('b2_signal', False)),
                    'b1_strength': int(latest.get('b1_strength', 0) or 0),
                    'b2_strength': int(latest.get('b2_strength', 0) or 0),
                    'b2_after_b1': bool(latest.get('b2_after_b1', False)),
                    'b2_after_consolidation': bool(latest.get('b2_after_consolidation', False)),
                    'b2_volume_double': bool(latest.get('b2_volume_double', False)),
                    'b2_strong_body': bool(latest.get('b2_strong_body', False)),
                    'b2_short_upper_shadow': bool(latest.get('b2_short_upper_shadow', False)),
                    'b2_shape_ready': bool(latest.get('b2_shape_ready', False)),
                    'perfect_b1': bool(latest.get('perfect_b1', False)),
                    'standard_b1': bool(latest.get('standard_b1', False)),
                    'weak_b1': bool(latest.get('weak_b1', False)),
                    'b1_rise_on_volume': bool(latest.get('b1_rise_on_volume', False)),
                    'b1_pullback_on_shrink': bool(latest.get('b1_pullback_on_shrink', False)),
                    'b1_extreme_shrink': bool(latest.get('b1_extreme_shrink', False)),
                    'b1_white_not_broken': bool(latest.get('b1_white_not_broken', False)),
                    'b1_from_yellow_zone': bool(latest.get('b1_from_yellow_zone', False)),
                    'b1_step_pullback': bool(latest.get('b1_step_pullback', False)),
                    'single_pin_low20': bool(latest.get('single_pin_low20', False)),
                    'single_pin_four_zero': bool(latest.get('single_pin_four_zero', False)),
                    'single_pin_white_cross_red': bool(latest.get('single_pin_white_cross_red', False)),
                    'single_pin_white_cross_yellow': bool(latest.get('single_pin_white_cross_yellow', False)),
                    'brick_exec_ready': bool(latest.get('brick_exec_ready', False)),
                    'brick_red_turn': bool(latest.get('brick_red_turn', False)),
                    'brick_green_turn': bool(latest.get('brick_green_turn', False)),
                    'brick_formula_signal': bool(latest.get('brick_formula_signal', False)),
                    'brick_formula_strong_signal': bool(latest.get('brick_formula_strong_signal', False)),
                    'brick_formula_turn_red': bool(latest.get('brick_formula_turn_red', False)),
                    'line_a_core': bool(latest.get('standard_b1', False)) and bool(latest.get('brick_formula_signal', False)) and bool(float(latest.get('mf_amount_5', 0) or 0) > 0),
                    'rotation_support': bool(latest.get('rotation_support', False)),
                    'rotation_support_level': latest.get('rotation_support_level', 'none'),
                    'resonance_whitelist': row.get('industry', '') in resonance_whitelist,
                    'reason': '、'.join(tags),
                })
        results.sort(key=lambda x: (x['score'], x['pct_chg']), reverse=True)
        return results[:top_n]
