"""第二阶段：历史数据初始化/增量更新（第一版）"""

from pathlib import Path
import pandas as pd

from .backtest_data import BacktestDataLoader
from .local_data_store import LocalDataStore


class HistorySync:
    def __init__(self, token: str, project_root: str):
        self.project_root = Path(project_root)
        self.store = LocalDataStore(self.project_root / 'data')
        self.loader = BacktestDataLoader(token)

    def sync_stock_basic(self):
        df = self.loader.get_stock_basic()
        if df is None or df.empty:
            return {'status': 'empty', 'dataset': 'stock_basic'}
        self.store.save('meta', 'stock_basic', df)
        return {'status': 'ok', 'dataset': 'stock_basic', 'rows': len(df)}

    def sync_daily_for_code(self, ts_code: str, start_date: str, end_date: str):
        df = self.loader.get_daily(ts_code, start_date, end_date)
        self.store.append_dedup('daily', ts_code, df, subset=('trade_date',))
        return {'status': 'ok', 'dataset': 'daily', 'code': ts_code, 'rows': len(df)}

    def sync_daily_basic_for_code(self, ts_code: str, start_date: str, end_date: str):
        df = self.loader.get_daily_basic(ts_code, start_date, end_date)
        self.store.append_dedup('daily_basic', ts_code, df, subset=('trade_date',))
        return {'status': 'ok', 'dataset': 'daily_basic', 'code': ts_code, 'rows': len(df)}

    def sync_adj_factor_for_code(self, ts_code: str, start_date: str, end_date: str):
        df = self.loader.get_adj_factor(ts_code, start_date, end_date)
        self.store.append_dedup('adj_factor', ts_code, df, subset=('trade_date',))
        return {'status': 'ok', 'dataset': 'adj_factor', 'code': ts_code, 'rows': len(df)}

    def sync_index_daily(self, index_code: str, start_date: str, end_date: str):
        df = self.loader.get_index_daily(index_code, start_date, end_date)
        self.store.append_dedup('index_daily', index_code, df, subset=('trade_date',))
        return {'status': 'ok', 'dataset': 'index_daily', 'code': index_code, 'rows': len(df)}

    def sync_moneyflow_for_code(self, ts_code: str, start_date: str, end_date: str):
        df = self.loader.get_moneyflow(ts_code, start_date, end_date)
        self.store.append_dedup('moneyflow', ts_code, df, subset=('trade_date',))
        return {'status': 'ok', 'dataset': 'moneyflow', 'code': ts_code, 'rows': len(df)}

    def sync_hkhold_for_code(self, ts_code: str, start_date: str, end_date: str):
        df = self.loader.get_hkhold(ts_code, start_date, end_date)
        self.store.append_dedup('hkhold', ts_code, df, subset=('trade_date',))
        return {'status': 'ok', 'dataset': 'hkhold', 'code': ts_code, 'rows': len(df)}

    def sync_margin(self, exchange_id: str, start_date: str, end_date: str):
        df = self.loader.get_margin(exchange_id, start_date, end_date)
        self.store.append_dedup('margin', exchange_id, df, subset=('trade_date',))
        return {'status': 'ok', 'dataset': 'margin', 'exchange_id': exchange_id, 'rows': len(df)}

    def sync_margin_detail_for_code(self, ts_code: str, start_date: str, end_date: str):
        df = self.loader.get_margin_detail(ts_code, start_date, end_date)
        self.store.append_dedup('margin_detail', ts_code, df, subset=('trade_date',))
        return {'status': 'ok', 'dataset': 'margin_detail', 'code': ts_code, 'rows': len(df)}

    def sync_bundle_for_code(self, ts_code: str, start_date: str, end_date: str):
        return {
            'daily': self.sync_daily_for_code(ts_code, start_date, end_date),
            'daily_basic': self.sync_daily_basic_for_code(ts_code, start_date, end_date),
            'adj_factor': self.sync_adj_factor_for_code(ts_code, start_date, end_date),
            'moneyflow': self.sync_moneyflow_for_code(ts_code, start_date, end_date),
            'hkhold': self.sync_hkhold_for_code(ts_code, start_date, end_date),
            'margin_detail': self.sync_margin_detail_for_code(ts_code, start_date, end_date),
        }
