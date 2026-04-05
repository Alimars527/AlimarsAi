from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAILY_CSV = ROOT / 'phase3_daily_log.csv'
WEEKLY_CSV = ROOT / 'phase3_weekly_summary.csv'


def safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


def load_daily_rows():
    if not DAILY_CSV.exists():
        return []
    with DAILY_CSV.open('r', encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def group_by_week(rows):
    groups = defaultdict(list)
    for row in rows:
        d = (row.get('trade_date') or '').strip()
        if len(d) >= 8:
            week_key = d[:8]
        else:
            week_key = 'unknown'
        groups[week_key].append(row)
    return groups


def summarize(rows):
    by_tier = {'strong_confirm': [], 'assist_confirm': [], 'front_only': []}
    executed_count = 0
    for row in rows:
        tier = (row.get('secondary_confirm_tier') or '').strip()
        if tier in by_tier:
            by_tier[tier].append(row)
        if (row.get('executed') or '').strip().lower() in {'1', 'true', 'yes', 'y', '是'}:
            executed_count += 1

    def stats(items):
        vals = []
        for r in items:
            v = safe_float(r.get('exit_result'))
            if v is not None:
                vals.append(v)
        if not vals:
            return '', ''
        win_rate = sum(1 for v in vals if v > 0) / len(vals)
        avg_return = sum(vals) / len(vals)
        return round(win_rate, 4), round(avg_return, 4)

    s_wr, s_avg = stats(by_tier['strong_confirm'])
    a_wr, a_avg = stats(by_tier['assist_confirm'])
    f_wr, f_avg = stats(by_tier['front_only'])

    return {
        'strong_confirm_count': len(by_tier['strong_confirm']),
        'assist_confirm_count': len(by_tier['assist_confirm']),
        'front_only_count': len(by_tier['front_only']),
        'executed_count': executed_count,
        'strong_win_rate': s_wr,
        'strong_avg_return': s_avg,
        'assist_win_rate': a_wr,
        'assist_avg_return': a_avg,
        'front_only_win_rate': f_wr,
        'front_only_avg_return': f_avg,
    }


def write_weekly(rows_by_week):
    with WEEKLY_CSV.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'week_start', 'week_end', 'strong_confirm_count', 'assist_confirm_count', 'front_only_count',
            'executed_count', 'strong_win_rate', 'strong_avg_return', 'assist_win_rate', 'assist_avg_return',
            'front_only_win_rate', 'front_only_avg_return', 'key_deviations', 'decision_notes'
        ])
        for week_key, rows in sorted(rows_by_week.items()):
            dates = sorted((r.get('trade_date') or '').strip() for r in rows if (r.get('trade_date') or '').strip())
            start = dates[0] if dates else week_key
            end = dates[-1] if dates else week_key
            s = summarize(rows)
            writer.writerow([
                start, end,
                s['strong_confirm_count'], s['assist_confirm_count'], s['front_only_count'],
                s['executed_count'], s['strong_win_rate'], s['strong_avg_return'],
                s['assist_win_rate'], s['assist_avg_return'],
                s['front_only_win_rate'], s['front_only_avg_return'],
                '', ''
            ])


def main():
    rows = load_daily_rows()
    rows_by_week = group_by_week(rows)
    write_weekly(rows_by_week)
    print(f'built weekly summary -> {WEEKLY_CSV}')


if __name__ == '__main__':
    main()
