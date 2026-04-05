import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.history_sync import HistorySync
from quant.config import load_settings


if __name__ == '__main__':
    settings = load_settings()
    token = settings['data']['tushare_token']
    sync = HistorySync(token, str(project_root))

    print(sync.sync_stock_basic())
    print(sync.sync_index_daily('000001.SH', '20250101', '20260320'))

    sample_codes = ['603986.SH', '601231.SH', '000028.SZ']
    for code in sample_codes:
        print(sync.sync_bundle_for_code(code, '20250101', '20260320'))
