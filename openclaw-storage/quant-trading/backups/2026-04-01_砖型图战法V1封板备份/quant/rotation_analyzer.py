from datetime import datetime, timedelta
import pandas as pd

from .data_loader import TushareClient
from .config import load_preferences


class RotationAnalyzer:
    def __init__(self):
        self.client = TushareClient()
        self.pro = self.client.pro
        self.preferences = load_preferences().get('candidate_filters', {})

    def analyze(self, end_date: str, lookback_days: int = 12, top_n: int = 5):
        stock_basic = self.client.fetch_stock_basic()
        if stock_basic.empty:
            return {
                'leaders': [],
                'continuation': [],
                'ambush': [],
                'avoid': []
            }

        start_dt = datetime.strptime(end_date, '%Y%m%d') - timedelta(days=lookback_days * 2)
        cal = self.pro.trade_cal(exchange='', start_date=start_dt.strftime('%Y%m%d'), end_date=end_date, is_open='1')
        dates = sorted(cal['cal_date'].tolist())[-lookback_days:]
        if not dates:
            return {
                'leaders': [],
                'continuation': [],
                'ambush': [],
                'avoid': []
            }

        universe = stock_basic.head(800)[['ts_code', 'industry']].copy()
        frames = []
        for d in dates:
            df = self.pro.daily(trade_date=d)
            if df is None or df.empty:
                continue
            df = df[['ts_code', 'trade_date', 'pct_chg']]
            df = df[df['ts_code'].isin(set(universe['ts_code']))]
            frames.append(df)
        if not frames:
            return {
                'leaders': [],
                'continuation': [],
                'ambush': [],
                'avoid': []
            }

        daily = pd.concat(frames, ignore_index=True)
        merged = daily.merge(universe, on='ts_code', how='left').dropna(subset=['industry'])

        by_day = merged.groupby(['trade_date', 'industry'])['pct_chg'].mean().reset_index()
        pivot = by_day.pivot(index='industry', columns='trade_date', values='pct_chg').fillna(0)
        latest_col = pivot.columns[-1]
        latest = pivot[latest_col]
        avg_all = pivot.mean(axis=1)
        recent3 = pivot.iloc[:, -3:].mean(axis=1) if pivot.shape[1] >= 3 else avg_all
        early = pivot.iloc[:, :-3].mean(axis=1) if pivot.shape[1] > 3 else avg_all

        leaders = []
        continuation = []
        ambush = []
        avoid = []

        prefer_industries = set(self.preferences.get('prefer_industries', []))
        avoid_industries = set(self.preferences.get('avoid_industries', []))

        for industry in pivot.index:
            l = float(latest.loc[industry])
            a = float(avg_all.loc[industry])
            r3 = float(recent3.loc[industry])
            e = float(early.loc[industry])
            bias = 0
            if industry in prefer_industries:
                bias = 0.4
            if industry in avoid_industries:
                bias = -0.6
            item = {
                'industry': industry,
                'latest_pct': round(l, 2),
                'avg_pct': round(a, 2),
                'recent3_pct': round(r3, 2),
                'bias': bias,
            }
            if l + bias > 2 or (r3 + bias > 1.2 and a + bias > 0.8):
                leaders.append(item)
            if r3 + bias > e and r3 + bias > 0.8:
                continuation.append(item)
            if e < 0 and r3 + bias > 0.5 and l > -0.5 and industry not in avoid_industries:
                ambush.append(item)
            if l < -1.5 and r3 < 0:
                avoid.append(item)

        sort_key = lambda x: (x['latest_pct'] + x.get('bias', 0), x['recent3_pct'] + x.get('bias', 0), x['avg_pct'])
        leaders = sorted(leaders, key=sort_key, reverse=True)[:top_n]
        continuation = sorted(continuation, key=sort_key, reverse=True)[:top_n]
        ambush = sorted(ambush, key=sort_key, reverse=True)[:top_n]
        avoid = sorted(avoid, key=lambda x: (x['latest_pct'], x['recent3_pct']))[:top_n]

        return {
            'leaders': leaders,
            'continuation': continuation,
            'ambush': ambush,
            'avoid': avoid,
        }
