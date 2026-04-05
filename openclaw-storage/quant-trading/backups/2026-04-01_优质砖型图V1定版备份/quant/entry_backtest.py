"""第二阶段：建议买入区间触发回测（第一版）"""

import pandas as pd

from .entry_calibrator import calibrate_entry_zone


class EntryBacktester:
    def simulate_entry_trigger(self, signal_df: pd.DataFrame, full_df: pd.DataFrame, hold_days: int = 1, strategy_tag: str = '主线趋势', shares: int = 100, simulator=None, price_mode: str = 'mid'):
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
            if idx + hold_days >= len(full_df):
                continue

            next_bar = full_df.iloc[idx + 1]
            candidate = {
                'close': sig.get('close'),
                'pct_chg': sig.get('pct_chg', 0),
                'strategy_tag': strategy_tag,
                'execution_style': sig.get('execution_style', ''),
            }
            entry_plan = calibrate_entry_zone(candidate)
            entry_low = entry_plan.get('entry_low')
            entry_high = entry_plan.get('entry_high')

            next_low = float(next_bar.get('low', 0) or 0)
            next_high = float(next_bar.get('high', 0) or 0)
            triggered = entry_low is not None and entry_high is not None and next_low <= entry_high and next_high >= entry_low
            if not triggered:
                rows.append({
                    'signal_date': trade_date,
                    'next_date': next_bar.get('trade_date'),
                    'triggered': False,
                    'entry_low': entry_low,
                    'entry_high': entry_high,
                })
                continue

            # 成交价假设：下沿 / 中值 / 上沿
            if price_mode == 'low':
                buy_price = float(entry_low)
            elif price_mode == 'high':
                buy_price = float(entry_high)
            else:
                buy_price = round((entry_low + entry_high) / 2, 4)
            sell_bar = full_df.iloc[idx + hold_days]
            sell_price = float(sell_bar.get('close'))

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
                'next_date': next_bar.get('trade_date'),
                'triggered': True,
                'entry_low': entry_low,
                'entry_high': entry_high,
                'buy_price': buy_price,
                'sell_date': sell_bar.get('trade_date'),
                'sell_price': sell_price,
                'buy_fee': round(buy_fee, 4),
                'sell_fee': round(sell_fee, 4),
                'net_pnl': round(net_pnl, 4),
                'return_pct': round(ret, 4),
            })
        return pd.DataFrame(rows)
