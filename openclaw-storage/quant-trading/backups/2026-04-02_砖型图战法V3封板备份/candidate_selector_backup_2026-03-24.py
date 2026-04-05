from pathlib import Path
import pandas as pd

from .data_loader import TushareClient
from .indicators import add_ma_features
from .config import load_preferences
from .style_classifier import classify_trend_style
from .moneyflow_features import add_moneyflow_features
from .hkhold_features import add_hkhold_features
from .margin_features import add_margin_features
from .brick_formula import add_brick_formula_flags
from .local_data_store import LocalDataStore


class CandidateSelector:
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
            return self.client.fetch_stock_daily(code, start_date=start_date, end_date=end_date)
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

    def select_from_hot_sectors(self, sector_rotation, trade_date: str, top_n: int = 8, focus_industries=None):
        stock_basic = self._load_stock_basic()
        if stock_basic.empty:
            return []

        hot_sector_names = [x['industry'] for x in sector_rotation[:5]] if sector_rotation else []
        if focus_industries:
            for industry in focus_industries:
                if industry not in hot_sector_names:
                    hot_sector_names.append(industry)
        universe = stock_basic[stock_basic['industry'].isin(hot_sector_names)].copy() if hot_sector_names else stock_basic.copy()
        if universe.empty:
            return []

        if self.preferences.get('exclude_st', True):
            universe = universe[~universe['name'].astype(str).str.upper().str.contains('ST', na=False)]
        avoid_industries = set(self.preferences.get('avoid_industries', []))
        if avoid_industries:
            universe = universe[~universe['industry'].isin(avoid_industries)]

        min_price = float(self.preferences.get('min_price', 0))
        max_price = float(self.preferences.get('max_price', 99999))
        preferred_industries = set(self.preferences.get('prefer_industries', []))
        preference_mode = self.preferences.get('preference_mode', 'weak_reference')

        picked = []
        start_date = '20260220'
        for _, row in universe.head(120).iterrows():
            code = row['ts_code']
            df = self._load_local_daily(code, start_date=start_date, end_date=trade_date)
            if df.empty or len(df) < 20:
                continue

            basic_df = self._load_local_daily_basic(code, start_date=start_date, end_date=trade_date)
            if not basic_df.empty and 'volume_ratio' in basic_df.columns:
                basic_df['volume_ratio'] = pd.to_numeric(basic_df['volume_ratio'], errors='coerce')
                df = df.merge(basic_df[['trade_date', 'volume_ratio']], on='trade_date', how='left')

            for col in ['open', 'high', 'low', 'close', 'vol', 'pct_chg']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            df = add_ma_features(df)
            df['ma5'] = df['close'].rolling(5).mean()
            df['ma10'] = df['close'].rolling(10).mean()
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
            df = add_brick_formula_flags(df)

            latest = df.iloc[-1]
            if latest['close'] < min_price or latest['close'] > max_price:
                continue

            score = 0
            reason = []
            preferred = row['industry'] in preferred_industries

            if latest['close'] > latest.get('ma5', latest['close']):
                score += 1
                reason.append('站上MA5')
            if latest['close'] > latest.get('ma10', latest['close']):
                score += 1
                reason.append('站上MA10')
            if preferred and preference_mode != 'none':
                score += 0.5
                reason.append('行业弱参考')
            if latest['pct_chg'] > 0:
                score += 1
                reason.append('当日收红')
            if len(df) >= 2 and latest['vol'] > df.iloc[-2]['vol']:
                score += 1
                reason.append('量能放大')
            high10 = pd.to_numeric(df.tail(10)['close'], errors='coerce').max()
            if pd.notna(high10) and latest['close'] >= high10 * 0.97:
                score += 1
                reason.append('接近10日高位')
            high20 = pd.to_numeric(df.tail(20)['high'], errors='coerce').max()
            if pd.notna(high20) and high20 != 0:
                drawdown = (high20 - latest['close']) / high20
                if drawdown <= 0.08:
                    score += 1
                    reason.append('强势回撤不深')
            if latest.get('ma5', latest['close']) >= latest.get('ma10', latest['close']) * 0.99:
                score += 1
                reason.append('短均线未走坏')
            if float(latest.get('mf_amount_5', 0) or 0) > 0:
                score += 1
                reason.append('近5日资金净流入')
            if bool(latest.get('brick_formula_signal', False)):
                score += 1.5
                reason.append('砖型图')
            if bool(latest.get('brick_formula_strong_signal', False)):
                score += 1
                reason.append('砖型图放量强化')
            if bool(latest.get('mf_divergence', False)):
                score -= 1
                reason.append('上涨资金背离')

            trend_style = classify_trend_style(latest)
            if score >= 4:
                picked.append({
                    'code': code,
                    'name': row['name'],
                    'industry': row['industry'],
                    'close': round(float(latest['close']), 2),
                    'pct_chg': round(float(latest['pct_chg']), 2),
                    'score': score,
                    'trend_style': trend_style,
                    'mf_divergence': bool(latest.get('mf_divergence', False)),
                    'mf_positive_5': bool(float(latest.get('mf_amount_5', 0) or 0) > 0),
                    'mf_positive_days_5_ok': bool(float(latest.get('mf_positive_days_5', 0) or 0) >= 3),
                    'brick_formula_signal': bool(latest.get('brick_formula_signal', False)),
                    'brick_formula_strong_signal': bool(latest.get('brick_formula_strong_signal', False)),
                    'reason': '、'.join(reason),
                })

        picked.sort(key=lambda x: (x['score'], x['pct_chg']), reverse=True)
        return picked[:top_n]
