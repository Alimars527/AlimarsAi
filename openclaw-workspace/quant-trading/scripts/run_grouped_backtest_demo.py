import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.grouped_backtest import GroupedBacktester


if __name__ == '__main__':
    industries = [
        '元器件',
        '电气设备',
        '医药商业',
        '化学制药',
        '软件服务',
    ]
    runner = GroupedBacktester(project_root)
    result = runner.run_by_industries(industries, strategy_name='主线趋势', hold_days=1, per_group_limit=30)
    print(result)
