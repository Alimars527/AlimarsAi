from pathlib import Path
from datetime import datetime
import pandas as pd
import tushare as ts

from .config import load_settings


class TushareClient:
    def __init__(self):
        settings = load_settings()
        token = settings['data']['tushare_token']
        self.pro = ts.pro_api(token)
        self.root = Path(__file__).resolve().parent.parent
        self.daily_dir = self.root / settings['data']['daily_dir']
        self.daily_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def normalize_code(code: str) -> str:
        code = code.strip()
        if code.endswith('.SH') or code.endswith('.SZ'):
            return code
        return f"{code}.SH" if code.startswith('6') else f"{code}.SZ"

    def fetch_stock_daily(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        ts_code = self.normalize_code(code)
        df = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return pd.DataFrame()
        return df.sort_values('trade_date').reset_index(drop=True)

    def fetch_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        df = self.pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return pd.DataFrame()
        return df.sort_values('trade_date').reset_index(drop=True)

    def fetch_daily_basic(self, code: str, trade_date: str) -> pd.DataFrame:
        ts_code = self.normalize_code(code)
        df = self.pro.daily_basic(ts_code=ts_code, start_date=trade_date, end_date=trade_date)
        return df if df is not None else pd.DataFrame()

    def fetch_stock_basic(self) -> pd.DataFrame:
        df = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,market,list_date')
        return df if df is not None else pd.DataFrame()

    def save_csv(self, df: pd.DataFrame, relative_path: str):
        path = self.daily_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, encoding='utf-8-sig')
        return path


def today_str():
    return datetime.now().strftime('%Y%m%d')
