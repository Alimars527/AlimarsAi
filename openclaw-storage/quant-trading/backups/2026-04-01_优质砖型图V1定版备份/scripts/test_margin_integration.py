import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.config import load_settings
from quant.history_sync import HistorySync

if __name__ == '__main__':
    settings = load_settings()
    sync = HistorySync(settings['data']['tushare_token'], str(project_root))

    res1 = sync.sync_margin('SSE', '20260301', '20260321')
    res2 = sync.sync_margin('SZSE', '20260301', '20260321')
    res3 = sync.sync_margin_detail_for_code('600036.SH', '20260301', '20260321')
    res4 = sync.sync_margin_detail_for_code('000333.SZ', '20260301', '20260321')
    print({'status': 'ok', 'margin_sse': res1, 'margin_szse': res2, 'detail_600036': res3, 'detail_000333': res4})
