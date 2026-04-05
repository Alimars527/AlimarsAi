import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from quant.style_grouped_backtest import StyleGroupedBacktester


if __name__ == '__main__':
    industries = ['元器件', '电气设备', '软件服务']
    runner = StyleGroupedBacktester(project_root)
    result = runner.run(industries, hold_days=1, per_group_limit=30)
    print(result)
