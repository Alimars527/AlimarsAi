#!/usr/bin/env python3
import json
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TRADE_DATE = '20260420'
CSV_PATH = ROOT / 'outputs' / f'daily_review_candidates_{TRADE_DATE}.csv'
MD_PATH = ROOT / 'outputs' / f'daily_review_candidates_{TRADE_DATE}.md'
JSON_PATH = ROOT / 'outputs' / f'daily_review_candidates_{TRADE_DATE}.json'

from quant.indicators import add_tactic_base_indicators
from quant.brick_formula import add_brick_formula_flags
from quant.levels import infer_key_levels
from quant.b1_experimental_v1 import b1_experimental_v1_ok


def add_bbi(df):
    out = df.copy()
    c = pd.to_numeric(out['close'], errors='coerce')
    out['bbi'] = (c.rolling(3).mean() + c.rolling(6).mean() + c.rolling(12).mean() + c.rolling(24).mean()) / 4
    return out


def j_threshold(td):
    return {'2023': -10, '2024': 0, '2025': 18}.get(str(td)[:4], 25)


def b1_v3_base_ok(df, idx):
    td = str(df.iloc[idx]['trade_date'])
    high = pd.to_numeric(df.iloc[idx]['high'], errors='coerce')
    white = pd.to_numeric(df.iloc[idx]['white_line'], errors='coerce')
    yellow = pd.to_numeric(df.iloc[idx]['yellow_line'], errors='coerce')
    jv = pd.to_numeric(df.iloc[idx]['kdj_j'], errors='coerce')
    mv = pd.to_numeric(df.iloc[idx]['total_mv_billion'], errors='coerce')
    base = (
        (pd.notna(jv) and jv < j_threshold(td))
        and (pd.notna(mv) and mv > 100)
        and (pd.notna(white) and pd.notna(yellow) and white > yellow)
        and (pd.notna(high) and pd.notna(white) and high >= white)
    )
    if not base:
        return False
    start = max(0, idx - 20)
    sub = df.iloc[start:idx+1].copy().reset_index(drop=True)
    if len(sub) < 8:
        return False
    close = pd.to_numeric(sub['close'], errors='coerce')
    peak_idx = close.idxmax()
    if peak_idx >= len(sub) - 1:
        return False
    pullback_len = len(sub) - 1 - peak_idx
    if pullback_len > 15:
        return False
    pb = sub.iloc[peak_idx+1:].copy()
    red = pd.to_numeric(pb['close'], errors='coerce') < pd.to_numeric(pb['open'], errors='coerce')
    red_pb = pb[red].copy()
    if len(red_pb) < 2 or 'vol' not in red_pb.columns:
        return False
    red_vol = pd.to_numeric(red_pb['vol'], errors='coerce').dropna().tolist()
    if len(red_vol) < 2:
        return False
    mid = max(1, len(red_vol) // 2)
    first = red_vol[:mid]; second = red_vol[mid:]
    return bool(second) and (sum(second) / len(second) < sum(first) / len(first))


def build_rotation_top5_map(meta):
    rows = []
    for row in meta[['ts_code', 'industry']].itertuples(index=False):
        p = ROOT / 'data' / 'daily' / f'{row.ts_code}.csv'
        if not p.exists() or not row.industry:
            continue
        try:
            df = pd.read_csv(p, usecols=['trade_date', 'pct_chg'], dtype={'trade_date': str})
            hit = df[df['trade_date'] == TRADE_DATE].copy()
            if hit.empty:
                continue
            hit['pct_chg'] = pd.to_numeric(hit['pct_chg'], errors='coerce')
            hit['industry'] = row.industry
            rows.append(hit[['trade_date', 'industry', 'pct_chg']])
        except Exception:
            continue
    if not rows:
        return {}, pd.DataFrame(columns=['industry', 'pct_chg', 'rank'])
    ind = pd.concat(rows, ignore_index=True)
    board = ind.groupby(['trade_date', 'industry'], as_index=False)['pct_chg'].mean().sort_values(['trade_date', 'pct_chg'], ascending=[True, False])
    board['rank'] = board.groupby('trade_date')['pct_chg'].rank(method='first', ascending=False)
    top5 = board[(board['trade_date'] == TRADE_DATE) & (board['rank'] <= 5)].copy()
    mp = top5.assign(flag=True).set_index(['trade_date', 'industry'])['flag'].to_dict()
    return mp, top5[['industry', 'pct_chg', 'rank']].sort_values('rank')


def main():
    meta = pd.read_csv(ROOT / 'data' / 'meta' / 'stock_basic.csv', dtype=str).fillna('')
    meta = meta[~meta['ts_code'].astype(str).str.endswith('.BJ')]
    meta = meta[~meta['name'].astype(str).str.contains('ST', case=False, na=False)]
    meta = meta[~meta['industry'].astype(str).isin(['银行'])]
    meta = meta[~meta['industry'].astype(str).str.contains('房地产', na=False)]

    omav = pd.read_csv(ROOT / 'data' / 'omav' / 'omav_daily_standardized_20260402.csv', dtype={'trade_date': str})
    omav_hit = omav[omav['trade_date'] == TRADE_DATE].copy()
    omav_row = omav_hit.iloc[0].to_dict() if not omav_hit.empty else {}
    rotation_map, top5_board = build_rotation_top5_map(meta)

    rows = []
    for row in meta[['ts_code', 'name', 'industry']].itertuples(index=False):
        p = ROOT / 'data' / 'daily' / f'{row.ts_code}.csv'
        pb = ROOT / 'data' / 'daily_basic' / f'{row.ts_code}.csv'
        if not p.exists() or not pb.exists():
            continue
        try:
            df = pd.read_csv(p, dtype={'trade_date': str})
            db = pd.read_csv(pb, dtype={'trade_date': str})
            if df.empty or not {'trade_date', 'open', 'high', 'low', 'close'}.issubset(df.columns):
                continue
            db = db[['trade_date', 'total_mv']].copy() if 'total_mv' in db.columns else pd.DataFrame(columns=['trade_date', 'total_mv'])
            db['total_mv_billion'] = pd.to_numeric(db['total_mv'], errors='coerce') / 10000.0
            df = df.sort_values('trade_date').reset_index(drop=True).merge(db[['trade_date', 'total_mv_billion']], on='trade_date', how='left')
            df = add_tactic_base_indicators(df)
            df = add_bbi(df)
            df = add_brick_formula_flags(df)
            hit = df[df['trade_date'] == TRADE_DATE]
            if hit.empty:
                continue
            idx = hit.index[-1]
            latest = df.loc[idx]
            support, pressure = infer_key_levels(df.iloc[max(0, idx-30):idx+1].copy())
            close_px = float(pd.to_numeric(latest['close'], errors='coerce'))
            bbi = float(pd.to_numeric(latest['bbi'], errors='coerce')) if pd.notna(pd.to_numeric(latest['bbi'], errors='coerce')) else None
            white = float(pd.to_numeric(latest['white_line'], errors='coerce')) if pd.notna(pd.to_numeric(latest['white_line'], errors='coerce')) else None
            yellow = float(pd.to_numeric(latest['yellow_line'], errors='coerce')) if pd.notna(pd.to_numeric(latest['yellow_line'], errors='coerce')) else None
            est_buy = round(close_px, 3)
            stop_loss = round(max(x for x in [bbi, support] if x is not None), 3) if any(x is not None for x in [bbi, support]) else None
            take_profit = round(min(x for x in [pressure] if x is not None), 3) if pressure is not None else round(close_px * 1.05, 3)
            rr = round((take_profit - est_buy) / max(est_buy - stop_loss, 0.001), 2) if stop_loss is not None and take_profit is not None else None

            b1_base = b1_v3_base_ok(df, idx)
            b1_experimental_v1 = b1_experimental_v1_ok(df, idx)
            brick_v1 = bool(latest.get('brick_raw_turn_red', False)) and bool(latest.get('brick_history_ok', False))
            z = pd.to_numeric(df['brick_formula_value'], errors='coerce').fillna(0)
            green = df['brick_formula_green'].fillna(False).astype(bool)
            brick_v3 = False
            if idx >= 4 and brick_v1:
                # 与回测引擎一致: 无OMAV数据时默认不拦截(bear=False, warn=False)
                rw = str(omav_row.get('omav_rotation_warning_flag', 'false')).lower() == 'true' if omav_row else False
                br = str(omav_row.get('omav_bear_regime_flag', 'false')).lower() == 'true' if omav_row else False
                omav_ok = not rw and not br
                rotation_ok = rotation_map.get((TRADE_DATE, row.industry), False)
                high_v = float(pd.to_numeric(latest['high'], errors='coerce'))
                white_v = float(pd.to_numeric(latest['white_line'], errors='coerce'))
                yellow_v = float(pd.to_numeric(latest['yellow_line'], errors='coerce'))
                brick_v3 = bool(
                    omav_ok and rotation_ok and
                    pd.notna(high_v) and pd.notna(white_v) and pd.notna(yellow_v) and
                    high_v >= white_v and white_v > yellow_v and
                    green.iloc[idx-1] and green.iloc[idx-2] and green.iloc[idx-3] and green.iloc[idx-4] and
                    z.iloc[idx-4] > z.iloc[idx-3] > z.iloc[idx-2] > z.iloc[idx-1] and
                    z.iloc[idx] >= z.iloc[idx-1]
                )
            b1_v3 = bool(b1_base and (rr is not None) and (rr >= 1.5))
            if not (b1_v3 or b1_experimental_v1 or brick_v3):
                continue
            strategy = []
            if b1_v3:
                strategy.append('B1_V3')
            if b1_experimental_v1:
                strategy.append('B1_EXPERIMENTAL_V1')
            if brick_v3:
                strategy.append('BRICK_V3')
            rows.append({
                'trade_date': TRADE_DATE,
                'ts_code': row.ts_code,
                'name': row.name,
                'industry': row.industry,
                'strategy_tags': '+'.join(strategy),
                'close': round(close_px, 3),
                'estimated_buy_cost': est_buy,
                'take_profit': take_profit,
                'stop_loss': stop_loss,
                'reward_risk_ratio': rr,
                'white_line': round(white, 3) if white is not None else None,
                'yellow_line': round(yellow, 3) if yellow is not None else None,
                'bbi': round(bbi, 3) if bbi is not None else None,
                'support': round(support, 3) if support is not None else None,
                'pressure': round(pressure, 3) if pressure is not None else None,
                'rotation_top5': 'Y' if rotation_map.get((TRADE_DATE, row.industry), False) else 'N',
                'brick_v1_hit': 'Y' if brick_v1 else 'N',
                'brick_v3_hit': 'Y' if brick_v3 else 'N',
                'b1_v3_hit': 'Y' if b1_v3 else 'N',
                'b1_experimental_v1_hit': 'Y' if b1_experimental_v1 else 'N',
                'note': '到区间后仍需结合盘面确认，不是到价即买'
            })
        except Exception:
            continue

    out = pd.DataFrame(rows)
    if not out.empty:
        def _sort_key(s):
            tags = str(s)
            if 'B1_V3' in tags and 'B1_EXPERIMENTAL_V1' in tags and 'BRICK_V3' in tags:
                return 0
            if 'B1_V3' in tags and 'B1_EXPERIMENTAL_V1' in tags:
                return 1
            if 'B1_V3' in tags and 'BRICK_V3' in tags:
                return 2
            if 'B1_EXPERIMENTAL_V1' in tags and 'BRICK_V3' in tags:
                return 3
            if 'B1_V3' in tags:
                return 4
            if 'B1_EXPERIMENTAL_V1' in tags:
                return 5
            if 'BRICK_V3' in tags:
                return 6
            return 9
        out['sort_key'] = out['strategy_tags'].map(_sort_key)
        out = out.sort_values(['sort_key', 'reward_risk_ratio', 'close'], ascending=[True, False, False]).drop(columns=['sort_key'])
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')

    md = []
    md.append(f'# {TRADE_DATE} 每日复盘候选表')
    md.append('')
    md.append('## 说明')
    md.append('- 候选池同时包含：B1_V3（位置质量过滤正式候选口径）、B1实验版V1、砖型图 V3')
    md.append('- 其中 B1_V3 按最优正式候选口径筛选：B1_V3 基础信号 + reward/risk >= 1.5')
    md.append('- 预计购入成本默认按当日收盘近似，仅作隔日计划参考')
    md.append('- 止盈/止损为本地策略参考位，最终仍需结合盘面确认')
    md.append('')
    if not top5_board.empty:
        md.append('## 当日板块轮动 Top5（砖型图V3参考）')
        for r in top5_board.itertuples(index=False):
            md.append(f'- {int(r.rank)}. {r.industry} ({round(float(r.pct_chg), 2)}%)')
        md.append('')
    md.append(f'## 候选数量: {len(out)}')
    md.append('')
    if out.empty:
        md.append('今日无命中候选。')
    else:
        md.append('|推荐序|代码|名称|行业|策略|B1_V3|B1实验版V1|砖型图 V3|预计购入成本|止盈|止损|RR|备注|')
        md.append('|---:|---|---|---|---|---|---|---|---:|---:|---:|---:|---|')
        for i, r in enumerate(out.head(80).itertuples(index=False), start=1):
            md.append(f'|{i}|{r.ts_code}|{r.name}|{r.industry}|{r.strategy_tags}|{"☑" if r.b1_v3_hit == "Y" else "☐"}|{"☑" if r.b1_experimental_v1_hit == "Y" else "☐"}|{"☑" if r.brick_v3_hit == "Y" else "☐"}|{r.estimated_buy_cost}|{r.take_profit}|{r.stop_loss}|{r.reward_risk_ratio}|{r.note}|')
    MD_PATH.write_text('\n'.join(md), encoding='utf-8')

    JSON_PATH.write_text(json.dumps({
        'trade_date': TRADE_DATE,
        'candidate_count': int(len(out)),
        'csv_path': str(CSV_PATH),
        'md_path': str(MD_PATH),
        'top5_board': top5_board.to_dict('records') if not top5_board.empty else [],
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(CSV_PATH)
    print(MD_PATH)
    print(JSON_PATH)

if __name__ == '__main__':
    main()
