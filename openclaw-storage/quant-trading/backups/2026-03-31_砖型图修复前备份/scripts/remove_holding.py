#!/usr/bin/env python3
from datetime import datetime
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.config import load_holdings, save_holdings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--code', required=True)
    args = parser.parse_args()

    data = load_holdings()
    holdings = data.get('holdings', [])
    holdings = [h for h in holdings if h['code'] != args.code]
    data['updated_at'] = datetime.now().isoformat()
    data['holdings'] = holdings
    save_holdings(data)
    print('持仓已删除')


if __name__ == '__main__':
    main()
