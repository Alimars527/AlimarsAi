"""第二阶段：本地历史数据仓（第一版）"""

from pathlib import Path
import pandas as pd


class LocalDataStore:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        for sub in ['daily', 'daily_basic', 'adj_factor', 'index_daily', 'moneyflow', 'hkhold', 'margin', 'margin_detail', 'meta']:
            (self.base_dir / sub).mkdir(parents=True, exist_ok=True)

    def _path(self, category: str, key: str) -> Path:
        safe_key = key.replace('/', '_')
        return self.base_dir / category / f'{safe_key}.csv'

    def exists(self, category: str, key: str) -> bool:
        return self._path(category, key).exists()

    def load(self, category: str, key: str) -> pd.DataFrame:
        path = self._path(category, key)
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path, dtype=str)

    def save(self, category: str, key: str, df: pd.DataFrame):
        path = self._path(category, key)
        if df is None or df.empty:
            return
        df.to_csv(path, index=False)

    def append_dedup(self, category: str, key: str, df: pd.DataFrame, subset=('trade_date',)):
        if df is None or df.empty:
            return
        old = self.load(category, key)
        merged = pd.concat([old, df], ignore_index=True)
        merged = merged.drop_duplicates(subset=list(subset), keep='last')
        if 'trade_date' in merged.columns:
            merged = merged.sort_values('trade_date')
        self.save(category, key, merged)
