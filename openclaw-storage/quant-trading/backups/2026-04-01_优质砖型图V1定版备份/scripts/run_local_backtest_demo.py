import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.local_backtest import LocalBacktester


if __name__ == '__main__':
    backtester = LocalBacktester(project_root)
    for code in ['603986.SH', '601231.SH', '000028.SZ']:
        print(backtester.run_single_code(code, strategy_name='主线趋势', hold_days=1))
