#!/usr/bin/env python3
from datetime import datetime, timedelta
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.config import load_holdings, load_settings
from quant.data_loader import TushareClient
from quant.market_regime import evaluate_index
from quant.sector_rotation import compute_sector_rotation
from quant.holdings_review import HoldingsReviewer
from quant.trade_planner import build_trade_plan
from quant.candidate_selector import CandidateSelector
from quant.full_market_scan import FullMarketScanner
from quant.narrative import build_narrative
from quant.rotation_analyzer import RotationAnalyzer
from quant.execution_filter import filter_for_next_day
from quant.priority_ranker import split_candidate_buckets


def main():
    settings = load_settings()
    holdings_data = load_holdings()
    holdings = holdings_data.get('holdings', [])
    if not holdings:
        raise SystemExit('当前没有持仓，请先更新 config/holdings.yaml')

    today = datetime.now()
    start_date = (today - timedelta(days=20)).strftime('%Y%m%d')
    end_date = today.strftime('%Y%m%d')

    client = TushareClient()
    reviewer = HoldingsReviewer()
    selector = CandidateSelector()
    scanner = FullMarketScanner()
    rotation_analyzer = RotationAnalyzer()

    sh_index = client.fetch_index_daily('000001.SH', start_date, end_date)
    regime = evaluate_index(sh_index)

    stock_basic = client.fetch_stock_basic()
    daily_frames = []
    for item in holdings:
        code = client.normalize_code(item['code'])
        df = client.fetch_stock_daily(code, end_date, end_date)
        if not df.empty:
            daily_frames.append(df)
    combined_daily = __import__('pandas').concat(daily_frames, ignore_index=True) if daily_frames else __import__('pandas').DataFrame()
    sector_rotation = compute_sector_rotation(combined_daily, stock_basic)

    reviews = [reviewer.review_one(item, start_date, end_date) for item in holdings]
    market_summary = {'regime': regime.regime, 'score': regime.score, 'summary': regime.summary}
    rotation_report = rotation_analyzer.analyze(end_date)
    hot_candidates = selector.select_from_hot_sectors(sector_rotation, end_date)
    scan_candidates = scanner.scan(end_date)
    merged_candidates = hot_candidates[:]
    existing = {c['code'] for c in merged_candidates}
    for c in scan_candidates:
        if c['code'] not in existing:
            merged_candidates.append(c)
    candidates = filter_for_next_day(merged_candidates[:12])
    candidates = [
        c for c in candidates
        if bool(c.get('b1_v3', False))
        or bool(c.get('b1_experimental_v1', False))
        or bool(c.get('brick_v3', False))
    ]
    focus_candidates, watch_candidates, avoid_chase_candidates = split_candidate_buckets(candidates)

    md = build_trade_plan(reviews, market_summary, sector_rotation, candidates, rotation_report)
    narrative = build_narrative(market_summary, sector_rotation, reviews, candidates, rotation_report)
    md = narrative + '\n\n' + md
    out_md = ROOT / settings['report']['output_markdown_latest']
    out_json = ROOT / settings['report']['output_json']
    out_md.write_text(md, encoding='utf-8')
    brick_base = [c for c in candidates if c.get('brick_v3', False)]
    brick_a = [c for c in brick_base if c.get('brick_a_group_ok')]
    brick_ab = [c for c in brick_a if c.get('brick_b_group_ok')]
    brick_abc = [c for c in brick_ab if c.get('brick_c_group_ok')]

    out_json.write_text(json.dumps({
        'generated_at': datetime.now().isoformat(),
        'market': market_summary,
        'sector_rotation': sector_rotation,
        'rotation_report': rotation_report,
        'holdings': reviews,
        'candidates': candidates,
        'focus_candidates': focus_candidates,
        'watch_candidates': watch_candidates,
        'avoid_chase_candidates': avoid_chase_candidates,
        'brick_layers': {
            'base_count': len(brick_base),
            'a_group': brick_a,
            'ab_group': brick_ab,
            'abc_group': brick_abc,
        },
    }, ensure_ascii=False, indent=2), encoding='utf-8')

    dated = ROOT / settings['report']['output_markdown_dir'] / f"{today.strftime('%Y-%m-%d')}.md"
    dated.write_text(md, encoding='utf-8')
    print(f'日报已生成: {out_md}')
    print(f'摘要已生成: {out_json}')


if __name__ == '__main__':
    main()
