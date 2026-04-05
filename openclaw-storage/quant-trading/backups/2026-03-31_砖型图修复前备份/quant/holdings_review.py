from .data_loader import TushareClient
from .indicators import add_ma_features
from .scenario_planner import build_scenarios
from .levels import infer_key_levels


class HoldingsReviewer:
    def __init__(self):
        self.client = TushareClient()

    def review_one(self, item, start_date: str, end_date: str):
        code = item['code']
        df = self.client.fetch_stock_daily(code, start_date, end_date)
        if df.empty:
            return {
                'code': code,
                'name': item.get('name', code),
                'error': '无日线数据'
            }
        df = add_ma_features(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else latest
        cost = float(item['cost'])
        qty = int(item['quantity'])
        total_pnl = latest['close'] / cost - 1
        day_pnl = latest['close'] / prev['close'] - 1 if prev['close'] else 0
        support, pressure = infer_key_levels(df)

        status = 'hold'
        if latest['close'] < support * 0.985:
            status = 'weak'
        elif latest['close'] > pressure * 0.98:
            status = 'strong'

        scenarios = build_scenarios(float(latest['close']), support, pressure)
        return {
            'code': code,
            'name': item.get('name', code),
            'close': round(float(latest['close']), 2),
            'pct_chg': round(float(latest['pct_chg']), 2),
            'cost': cost,
            'quantity': qty,
            'position_shares': qty * 100,
            'market_value': round(float(latest['close']) * qty * 100, 2),
            'total_pnl_pct': round(float(total_pnl) * 100, 2),
            'day_pnl_pct': round(float(day_pnl) * 100, 2),
            'support': round(support, 2) if support else None,
            'pressure': round(pressure, 2) if pressure else None,
            'status': status,
            'plan': self._make_plan(float(latest['close']), support, pressure),
            'scenarios': scenarios,
        }

    @staticmethod
    def _make_plan(close, support, pressure):
        if support is None or pressure is None:
            return '数据不足，观察为主'
        if close >= pressure * 0.97:
            return f'接近压力位{pressure:.2f}，若明日不能放量突破则谨慎追高'
        if close <= support * 1.02:
            return f'接近支撑位{support:.2f}，观察是否能企稳反弹'
        return f'处于支撑{support:.2f}与压力{pressure:.2f}之间，按计划持有观察'
