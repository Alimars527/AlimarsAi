"""第二阶段：简化买卖模拟器（第一版）"""

import pandas as pd


class SimpleSimulator:
    def __init__(self, commission_rate=0.000086, min_commission=5, stamp_tax_sell=0.0005, lot_size=100):
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.stamp_tax_sell = stamp_tax_sell
        self.lot_size = lot_size

    def set_fee_config(self, commission_rate=None, min_commission=None, stamp_tax_sell=None, lot_size=None):
        if commission_rate is not None:
            self.commission_rate = commission_rate
        if min_commission is not None:
            self.min_commission = min_commission
        if stamp_tax_sell is not None:
            self.stamp_tax_sell = stamp_tax_sell
        if lot_size is not None:
            self.lot_size = lot_size

    def _buy_fee(self, price, shares):
        amount = price * shares
        return max(amount * self.commission_rate, self.min_commission)

    def _sell_fee(self, price, shares):
        amount = price * shares
        commission = max(amount * self.commission_rate, self.min_commission)
        stamp_tax = amount * self.stamp_tax_sell
        return commission + stamp_tax

    def simulate_hold_period(self, df: pd.DataFrame, hold_days: int = 1, shares=None):
        if df is None or df.empty or len(df) <= hold_days:
            return pd.DataFrame()

        shares = shares or self.lot_size
        rows = []
        for i in range(len(df) - hold_days):
            buy_row = df.iloc[i]
            sell_row = df.iloc[i + hold_days]
            buy_price = buy_row.get('close')
            sell_price = sell_row.get('close')
            if not buy_price or not sell_price:
                continue

            buy_amount = buy_price * shares
            sell_amount = sell_price * shares
            buy_fee = self._buy_fee(buy_price, shares)
            sell_fee = self._sell_fee(sell_price, shares)
            net_pnl = sell_amount - sell_fee - buy_amount - buy_fee
            ret = net_pnl / (buy_amount + buy_fee) * 100

            rows.append({
                'buy_date': buy_row.get('trade_date'),
                'sell_date': sell_row.get('trade_date'),
                'buy_price': buy_price,
                'sell_price': sell_price,
                'shares': shares,
                'buy_fee': round(buy_fee, 4),
                'sell_fee': round(sell_fee, 4),
                'net_pnl': round(net_pnl, 4),
                'return_pct': round(ret, 4),
            })
        return pd.DataFrame(rows)
