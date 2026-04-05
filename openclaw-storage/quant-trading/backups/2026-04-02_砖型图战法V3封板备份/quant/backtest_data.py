"""第二阶段：回测数据层（第一版骨架）"""

from pathlib import Path
from typing import Optional
import pandas as pd
import tushare as ts


class BacktestDataLoader:
    def __init__(self, token: str, cache_dir: Optional[str] = None):
        self.token = token
        self.pro = ts.pro_api(token)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        df = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return pd.DataFrame()
        return df.sort_values('trade_date').reset_index(drop=True)

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        df = self.pro.daily_basic(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return pd.DataFrame()
        return df.sort_values('trade_date').reset_index(drop=True)

    def get_stock_basic(self) -> pd.DataFrame:
        df = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,market,list_date')
        if df is None or df.empty:
            return pd.DataFrame()
        return df

    def get_adj_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        df = self.pro.adj_factor(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return pd.DataFrame()
        return df.sort_values('trade_date').reset_index(drop=True)

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        df = self.pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return pd.DataFrame()
        return df.sort_values('trade_date').reset_index(drop=True)

    def get_moneyflow(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        from datetime import datetime, timedelta
        start = datetime.strptime(start_date, '%Y%m%d')
        end = datetime.strptime(end_date, '%Y%m%d')
        parts = []
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=365 * 2 - 1), end)
            df = self.pro.moneyflow(
                ts_code=ts_code,
                start_date=cursor.strftime('%Y%m%d'),
                end_date=chunk_end.strftime('%Y%m%d')
            )
            if df is not None and not df.empty:
                parts.append(df)
            cursor = chunk_end + timedelta(days=1)
        if not parts:
            return pd.DataFrame()
        merged = pd.concat(parts, ignore_index=True)
        merged = merged.drop_duplicates(subset=['trade_date'], keep='last')
        return merged.sort_values('trade_date').reset_index(drop=True)

    def get_hkhold(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        from datetime import datetime, timedelta
        start = datetime.strptime(start_date, '%Y%m%d')
        end = datetime.strptime(end_date, '%Y%m%d')
        parts = []
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=180 - 1), end)
            df = self.pro.hk_hold(
                ts_code=ts_code,
                start_date=cursor.strftime('%Y%m%d'),
                end_date=chunk_end.strftime('%Y%m%d')
            )
            if df is not None and not df.empty:
                parts.append(df)
            cursor = chunk_end + timedelta(days=1)
        if not parts:
            return pd.DataFrame()
        merged = pd.concat(parts, ignore_index=True)
        merged = merged.drop_duplicates(subset=['trade_date'], keep='last')
        return merged.sort_values('trade_date').reset_index(drop=True)

    def get_margin(self, exchange_id: str, start_date: str, end_date: str) -> pd.DataFrame:
        df = self.pro.margin(exchange_id=exchange_id, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return pd.DataFrame()
        return df.sort_values('trade_date').reset_index(drop=True)

    def get_margin_detail(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        from datetime import datetime, timedelta
        start = datetime.strptime(start_date, '%Y%m%d')
        end = datetime.strptime(end_date, '%Y%m%d')
        parts = []
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=180 - 1), end)
            df = self.pro.margin_detail(
                ts_code=ts_code,
                start_date=cursor.strftime('%Y%m%d'),
                end_date=chunk_end.strftime('%Y%m%d')
            )
            if df is not None and not df.empty:
                parts.append(df)
            cursor = chunk_end + timedelta(days=1)
        if not parts:
            return pd.DataFrame()
        merged = pd.concat(parts, ignore_index=True)
        merged = merged.drop_duplicates(subset=['trade_date'], keep='last')
        return merged.sort_values('trade_date').reset_index(drop=True)
