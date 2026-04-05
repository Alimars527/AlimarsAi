from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / 'outputs' / 'latest_summary.json'
CSV_PATH = ROOT / 'phase3_daily_log.csv'


def load_summary():
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(f'Missing summary file: {SUMMARY_PATH}')
    with SUMMARY_PATH.open('r', encoding='utf-8') as f:
        return json.load(f)


def append_rows(summary):
    trade_date = str(summary.get('trade_date', ''))
    market = summary.get('market', {}) or {}
    regime = market.get('regime', '')

    candidates = summary.get('candidates', [])
    if isinstance(candidates, dict):
        focus = candidates.get('focus', []) or []
        watch = candidates.get('watch', []) or []
        all_candidates = focus + watch
    elif isinstance(candidates, list):
        all_candidates = candidates
    else:
        all_candidates = []

    with CSV_PATH.open('a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        for c in all_candidates:
            entry = c.get('entry_plan', {}) or {}
            writer.writerow([
                trade_date,
                regime,
                c.get('code', ''),
                c.get('name', ''),
                c.get('industry', ''),
                c.get('strategy_tag', ''),
                c.get('trend_tier', ''),
                c.get('secondary_confirm_tier', ''),
                c.get('priority_score', ''),
                entry.get('entry_low', ''),
                entry.get('entry_high', ''),
                entry.get('do_not_chase_above', ''),
                '', '', '', '', '', '', '', '',
            ])


def main():
    summary = load_summary()
    append_rows(summary)
    print(f'exported phase3 daily candidates -> {CSV_PATH}')


if __name__ == '__main__':
    main()
