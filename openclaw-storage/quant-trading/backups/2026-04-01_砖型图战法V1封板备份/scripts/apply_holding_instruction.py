#!/usr/bin/env python3
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.holding_parser import apply_holding_instruction


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('text', help='自然语言持仓变更指令')
    args = parser.parse_args()
    result = apply_holding_instruction(args.text)
    print(result['message'])


if __name__ == '__main__':
    main()
