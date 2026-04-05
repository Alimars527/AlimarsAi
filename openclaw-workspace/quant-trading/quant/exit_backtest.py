"""第二阶段：带卖点模型的执行回测（第一版）"""

import pandas as pd

from .entry_calibrator import calibrate_entry_zone
from .exit_engine import ExitEngine


class ExitBacktester:
    def __init__(self):
        self.exit_engine = ExitEngine()

    def simulate(self, signal_df: pd.DataFrame, full_df: pd.DataFrame, strategy_tag='主线趋势', shares=100, simulator=None, price_mode='low'):
        if signal_df is None or signal_df.empty or full_df is None or full_df.empty:
            return pd.DataFrame()

        full_df = full_df.copy().reset_index(drop=True)
        rows = []
        for _, sig in signal_df.iterrows():
            trade_date = sig['trade_date']
            idx_list = full_df.index[full_df['trade_date'] == trade_date].tolist()
            if not idx_list:
                continue
            idx = idx_list[0]
            if idx + 1 >= len(full_df):
                continue

            candidate = {
                'close': sig.get('close'),
                'pct_chg': sig.get('pct_chg', 0),
                'strategy_tag': strategy_tag,
                'execution_style': sig.get('execution_style', ''),
            }
            entry_plan = calibrate_entry_zone(candidate)
            entry_low = entry_plan.get('entry_low')
            entry_high = entry_plan.get('entry_high')
            next_bar = full_df.iloc[idx + 1]
            next_low = float(next_bar.get('low', 0) or 0)
            next_high = float(next_bar.get('high', 0) or 0)
            next_open = float(next_bar.get('open', 0) or 0)
            prev_close = float(full_df.iloc[idx].get('close', 0) or 0)
            triggered = entry_low is not None and entry_high is not None and next_low <= entry_high and next_high >= entry_low
            if not triggered:
                continue

            if price_mode == 'high':
                buy_price = float(entry_high)
            elif price_mode == 'mid':
                buy_price = round((entry_low + entry_high) / 2, 4)
            else:
                buy_price = float(entry_low)

            future_bars = []
            for j in range(idx + 1, min(idx + 5, len(full_df))):
                future_bars.append(full_df.iloc[j].to_dict())
            exit_decision = self.exit_engine.decide_exit(
                buy_price,
                future_bars,
                strategy_name=strategy_tag,
                prev_close=prev_close,
                buy_open=next_open,
                industry=sig.get('industry', ''),
            )
            sell_price = float(exit_decision['exit_price'])

            if simulator is not None:
                buy_amount = buy_price * shares
                sell_amount = sell_price * shares
                buy_fee = simulator._buy_fee(buy_price, shares)
                sell_fee = simulator._sell_fee(sell_price, shares)
                net_pnl = sell_amount - sell_fee - buy_amount - buy_fee
                ret = net_pnl / (buy_amount + buy_fee) * 100
            else:
                buy_fee = 0
                sell_fee = 0
                net_pnl = (sell_price - buy_price) * shares
                ret = (sell_price / buy_price - 1) * 100

            rows.append({
                'signal_date': trade_date,
                'buy_date': next_bar.get('trade_date'),
                'buy_price': buy_price,
                'open_scenario': exit_decision.get('open_scenario'),
                'exit_type': exit_decision['exit_type'],
                'sell_date': exit_decision['exit_date'],
                'sell_price': sell_price,
                'hold_days': exit_decision['hold_days'],
                'net_pnl': round(net_pnl, 4),
                'return_pct': round(ret, 4),
            })
        return pd.DataFrame(rows)
