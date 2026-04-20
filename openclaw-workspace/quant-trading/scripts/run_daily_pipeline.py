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
from quant.narrative import build_narrative
from quant.rotation_analyzer import RotationAnalyzer

DAILY_REVIEW_FILENAME = '{date}_每日复盘.md'


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
    rotation_analyzer = RotationAnalyzer()

    # Step 1: 数据校验 - 拉取指数数据
    sh_index = client.fetch_index_daily('000001.SH', start_date, end_date)
    regime = evaluate_index(sh_index)

    # Step 2: 板块轮动
    stock_basic = client.fetch_stock_basic()
    daily_frames = []
    for item in holdings:
        code = client.normalize_code(item['code'])
        df = client.fetch_stock_daily(code, end_date, end_date)
        if not df.empty:
            daily_frames.append(df)
    combined_daily = __import__('pandas').concat(daily_frames, ignore_index=True) if daily_frames else __import__('pandas').DataFrame()
    sector_rotation = compute_sector_rotation(combined_daily, stock_basic)

    # Step 3: 持仓操作建议
    reviews = [reviewer.review_one(item, start_date, end_date) for item in holdings]
    market_summary = {'regime': regime.regime, 'score': regime.score, 'summary': regime.summary}
    rotation_report = rotation_analyzer.analyze(end_date)

    # NOTE: 热板块候选/全市场B1砖型图扫描/过滤 已移除，由 @候选票推荐 独立指令执行

    # Step 4: 生成报告（无候选票部分）
    md = build_trade_plan(reviews, market_summary, sector_rotation, [], rotation_report)
    narrative = build_narrative(market_summary, sector_rotation, reviews, [], rotation_report)
    md = narrative + '\n\n' + md

    # 写 outputs/latest_plan.md
    out_md = ROOT / settings['report']['output_markdown_latest']
    out_md.write_text(md, encoding='utf-8')

    # 写 outputs/latest_summary.json
    out_json = ROOT / settings['report']['output_json']
    out_json.write_text(json.dumps({
        'generated_at': datetime.now().isoformat(),
        'market': market_summary,
        'sector_rotation': sector_rotation,
        'rotation_report': rotation_report,
        'holdings': reviews,
        'candidates': [],
        'focus_candidates': [],
        'watch_candidates': [],
        'avoid_chase_candidates': [],
        'brick_layers': {
            'base_count': 0,
            'a_group': [],
            'ab_group': [],
            'abc_group': [],
        },
    }, ensure_ascii=False, indent=2), encoding='utf-8')

    # 写日期复盘文件：存在则更新，不存在则新建
    dated = ROOT / settings['report']['output_markdown_dir'] / DAILY_REVIEW_FILENAME.format(date=today.strftime('%Y-%m-%d'))
    if dated.exists():
        existing_md = dated.read_text(encoding='utf-8')
        # 找到分割点：如果已有"## 一、市场环境"等标记，替换对应段落
        # 否则追加到末尾
        section_markers = [
            '## 一、', '## 二、', '## 三、', '## 四、', '## 五、',
            '## 六、', '## 七、', '## 八、', '## 九、', '## 十、',
        ]
        has_sections = any(m in existing_md for m in section_markers)
        if has_sections:
            # 替换已有内容：保留"十、候选票推荐"及之后的内容（如果有）
            candidate_section = '## 十、候选票推荐'
            if candidate_section in existing_md:
                # 保留候选票推荐部分，只替换前面的日报主体
                idx = existing_md.index(candidate_section)
                preserved = existing_md[idx:]
                dated.write_text(md + '\n\n' + preserved, encoding='utf-8')
            else:
                dated.write_text(md, encoding='utf-8')
            action = '已更新'
        else:
            # 文件存在但无标准结构，直接覆盖
            dated.write_text(md, encoding='utf-8')
            action = '已更新'
    else:
        dated.write_text(md, encoding='utf-8')
        action = '已创建'

    print(f'日报{action}: {dated}')
    print(f'latest_plan: {out_md}')
    print(f'latest_summary: {out_json}')


if __name__ == '__main__':
    main()
