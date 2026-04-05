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
    parser.add_argument('--name', required=True)
    parser.add_argument('--cost', type=float, required=True)
    parser.add_argument('--quantity', type=int, required=True, help='手数')
    args = parser.parse_args()

    data = load_holdings()
    holdings = data.get('holdings', [])
    updated = False
    for item in holdings:
        if item['code'] == args.code:
            item.update({'name': args.name, 'cost': args.cost, 'quantity': args.quantity})
            updated = True
            break
    if not updated:
        holdings.append({'code': args.code, 'name': args.name, 'cost': args.cost, 'quantity': args.quantity})

    data['updated_at'] = datetime.now().isoformat()
    data['holdings'] = holdings
    save_holdings(data)
    print('持仓已更新')


if __name__ == '__main__':
    main()
