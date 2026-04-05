import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.batch_backtest import BatchBacktester


if __name__ == '__main__':
    runner = BatchBacktester(project_root)
    result = runner.run_sample(strategy_name='主线趋势', hold_days=1, sample_size=120)
    print(result)
