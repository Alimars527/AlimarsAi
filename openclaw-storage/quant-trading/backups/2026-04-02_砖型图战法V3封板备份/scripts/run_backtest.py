import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.backtest_runner import BacktestRunner


if __name__ == '__main__':
    runner = BacktestRunner(project_root)
    result = runner.run()
    print(result)
