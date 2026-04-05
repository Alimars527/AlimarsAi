"""第二阶段：按策略 + 开盘场景 + 行业差异化细化的规则化卖点模型（第三版）"""

from .industry_exit_policy import industry_exit_overrides


def get_exit_config(strategy_name: str, open_scenario: str = 'flat_open', industry: str = ''):
    if strategy_name == '主线趋势':
        base = {
            'take_profit_pct': 0.03,
            'stop_loss_pct': -0.025,
            'max_hold_days': 2,
            'exit_on_weak_close': True,
            'early_exit_on_red_day': True,
        }
        if open_scenario == 'high_open':
            base.update({'take_profit_pct': 0.02, 'stop_loss_pct': -0.02, 'max_hold_days': 1})
        elif open_scenario == 'low_open':
            base.update({'take_profit_pct': 0.025, 'stop_loss_pct': -0.02, 'max_hold_days': 2})
        base.update(industry_exit_overrides(industry, open_scenario))
        return base

    if strategy_name == '轮动补涨':
        base = {
            'take_profit_pct': 0.02,
            'stop_loss_pct': -0.02,
            'max_hold_days': 2,
            'exit_on_weak_close': True,
            'early_exit_on_red_day': False,
        }
        if open_scenario == 'high_open':
            base.update({'take_profit_pct': 0.015, 'max_hold_days': 1})
        elif open_scenario == 'low_open':
            base.update({'take_profit_pct': 0.02, 'stop_loss_pct': -0.018, 'max_hold_days': 1})
        return base

    base = {
        'take_profit_pct': 0.015,
        'stop_loss_pct': -0.02,
        'max_hold_days': 2,
        'exit_on_weak_close': True,
        'early_exit_on_red_day': False,
    }
    if open_scenario == 'high_open':
        base.update({'take_profit_pct': 0.012, 'max_hold_days': 1})
    elif open_scenario == 'low_open':
        base.update({'take_profit_pct': 0.015, 'stop_loss_pct': -0.018, 'max_hold_days': 1})
    return base


class ExitEngine:
    def __init__(self):
        pass

    def classify_open_scenario(self, prev_close: float, buy_open: float):
        if prev_close <= 0:
            return 'flat_open'
        gap = (buy_open / prev_close - 1) * 100
        if gap >= 1.5:
            return 'high_open'
        if gap <= -1.5:
            return 'low_open'
        return 'flat_open'

    def decide_exit(self, buy_price: float, bars, strategy_name='主线趋势', prev_close=None, buy_open=None, industry: str = ''):
        scenario = self.classify_open_scenario(prev_close or buy_price, buy_open or buy_price)
        cfg = get_exit_config(strategy_name, scenario, industry=industry)
        tp = cfg['take_profit_pct']
        sl = cfg['stop_loss_pct']
        max_hold = cfg['max_hold_days']
        exit_on_weak_close = cfg['exit_on_weak_close']
        early_exit_on_red_day = cfg.get('early_exit_on_red_day', False)

        for i, bar in enumerate(bars[:max_hold], 1):
            high = float(bar.get('high', 0) or 0)
            low = float(bar.get('low', 0) or 0)
            close = float(bar.get('close', 0) or 0)
            trade_date = bar.get('trade_date')

            if high >= buy_price * (1 + tp):
                return {
                    'exit_type': f'{scenario}_take_profit',
                    'hold_days': i,
                    'exit_price': round(buy_price * (1 + tp), 4),
                    'exit_date': trade_date,
                    'open_scenario': scenario,
                }

            if low <= buy_price * (1 + sl):
                return {
                    'exit_type': f'{scenario}_stop_loss',
                    'hold_days': i,
                    'exit_price': round(buy_price * (1 + sl), 4),
                    'exit_date': trade_date,
                    'open_scenario': scenario,
                }

            if i == 1 and exit_on_weak_close and close < buy_price:
                return {
                    'exit_type': f'{scenario}_weak_close_exit',
                    'hold_days': i,
                    'exit_price': close,
                    'exit_date': trade_date,
                    'open_scenario': scenario,
                }

            if i == 1 and early_exit_on_red_day and close < buy_price * 0.995:
                return {
                    'exit_type': f'{scenario}_early_red_exit',
                    'hold_days': i,
                    'exit_price': close,
                    'exit_date': trade_date,
                    'open_scenario': scenario,
                }

        last_bar = bars[min(len(bars), max_hold) - 1]
        return {
            'exit_type': f'{scenario}_time_exit',
            'hold_days': min(len(bars), max_hold),
            'exit_price': float(last_bar.get('close', 0) or 0),
            'exit_date': last_bar.get('trade_date'),
            'open_scenario': scenario,
        }
