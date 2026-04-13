#!/usr/bin/env python3
"""
每日收盘后数据同步脚本
- 同步上证指数日线
- 同步持仓股票日线
- 同步日线财务数据（市值等）
然后触发日报生成

用法: python daily_data_sync.py [TRADE_DATE]
不传参数则自动拉今天的数据
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import tushare as ts

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.config import load_holdings, load_settings


def get_trade_date():
    if len(sys.argv) >= 2:
        return sys.argv[1]
    # 自动：今天如果是交易日就今天，否则取上一个交易日
    today = datetime.now()
    return today.strftime('%Y%m%d')


def sync_index_daily(pro, trade_date: str, root: Path) -> int:
    """同步上证指数，返回新增条数"""
    # 取最近20天数据确保覆盖
    start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=25)).strftime('%Y%m%d')
    df = pro.index_daily(ts_code='000001.SH', start_date=start, end_date=trade_date)
    if df is None or df.empty:
        print(f"  [WARN] 上证指数{trade_date}无数据")
        return 0
    df = df.sort_values('trade_date')
    path = root / 'data' / 'index_daily' / '000001.SH.csv'
    existing = pd.read_csv(path, dtype=str) if path.exists() else pd.DataFrame()
    merged = pd.concat([existing, df]).drop_duplicates(subset='trade_date', keep='last').sort_values('trade_date')
    merged.to_csv(path, index=False)
    new_rows = len(df[df['trade_date'] == trade_date]) if 'trade_date' in df.columns else len(df)
    print(f"  [OK] 上证指数 -> {path.name}，今日:{trade_date}，新增{new_rows}条")
    return new_rows


def sync_stock_daily(pro, ts_code: str, trade_date: str, root: Path) -> dict:
    """同步单只股票日线，返回状态"""
    start = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=25)).strftime('%Y%m%d')
    df = pro.daily(ts_code=ts_code, start_date=start, end_date=trade_date)
    if df is None or df.empty:
        return {'status': 'no_data', 'code': ts_code}
    df = df.sort_values('trade_date')
    path = root / 'data' / 'daily' / f'{ts_code}.csv'
    existing = pd.read_csv(path, dtype=str) if path.exists() else pd.DataFrame()
    merged = pd.concat([existing, df]).drop_duplicates(subset='trade_date', keep='last').sort_values('trade_date')
    merged.to_csv(path, index=False)
    new_rows = len(df[df['trade_date'] == trade_date]) if 'trade_date' in df.columns else len(df)
    return {'status': 'ok', 'code': ts_code, 'new_rows': new_rows, 'close': df[df['trade_date'] == trade_date]['close'].values[0] if new_rows > 0 else None}


def sync_daily_basic(pro, ts_code: str, trade_date: str, root: Path) -> dict:
    """同步日线财务数据"""
    df = pro.daily_basic(ts_code=ts_code, start_date=trade_date, end_date=trade_date)
    if df is None or df.empty:
        return {'status': 'no_data', 'code': ts_code}
    path = root / 'data' / 'daily_basic' / f'{ts_code}.csv'
    existing = pd.read_csv(path, dtype=str) if path.exists() else pd.DataFrame()
    merged = pd.concat([existing, df]).drop_duplicates(subset='trade_date', keep='last').sort_values('trade_date')
    merged.to_csv(path, index=False)
    return {'status': 'ok', 'code': ts_code}


def main():
    settings = load_settings()
    holdings_data = load_holdings()
    holdings = holdings_data.get('holdings', [])
    
    trade_date = get_trade_date()
    today_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    print(f"\n=== 每日数据同步 {today_str} ===")
    print(f"目标交易日: {trade_date}")
    
    token = settings['data']['tushare_token']
    pro = ts.pro_api(token)
    
    # 1. 同步上证指数
    print("\n[1/3] 同步上证指数...")
    sync_index_daily(pro, trade_date, ROOT)
    
    # 2. 同步持仓股票
    print("\n[2/3] 同步持仓股票日线...")
    etf_codes = [h for h in holdings if 'ETF' in h.get('name', '') or h.get('code', '').startswith('15')]
    stock_codes = [h for h in holdings if h not in etf_codes]
    
    results = []
    for item in stock_codes:
        code = item['code']
        # 确保带后缀
        if not (code.endswith('.SH') or code.endswith('.SZ') or code.endswith('.BJ')):
            code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
        result = sync_stock_daily(pro, code, trade_date, ROOT)
        results.append(result)
        if result['status'] == 'ok':
            close = result.get('close', '?')
            print(f"  [OK] {code} 收盘:{close}")
        else:
            print(f"  [SKIP] {code} 无今日数据")
    
    # 3. 同步日线财务（持仓股）
    print("\n[3/3] 同步日线财务数据...")
    for item in stock_codes:
        code = item['code']
        if not (code.endswith('.SH') or code.endswith('.SZ') or code.endswith('.BJ')):
            code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
        sync_daily_basic(pro, code, trade_date, ROOT)
    
    print(f"\n=== 数据同步完成 {trade_date} ===\n")
    
    # 4. 触发日报生成
    print("[4/4] 触发日报生成...")
    import subprocess
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'run_daily_pipeline.py')],
        capture_output=True,
        text=True,
        timeout=120
    )
    if result.returncode == 0:
        print("  [OK] 日报生成成功")
        print(result.stdout.strip().split('\n')[-1])  # 最后一行
    else:
        print(f"  [ERROR] 日报生成失败: {result.stderr}")
    
    # 输出现场摘要
    summary_path = ROOT / 'outputs' / 'latest_summary.json'
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        holdings_info = summary.get('holdings', [])
        market_info = summary.get('market', {})
        print(f"\n=== 今日快照 ===")
        print(f"市场环境: {market_info.get('regime', '?')} ({market_info.get('summary', '')})")
        for h in holdings_info:
            if 'error' in h:
                print(f"  {h.get('name', h.get('code'))}: {h.get('error')}")
            else:
                close = h.get('close', '?')
                pct = h.get('pct_chg', 0)
                total_pnl = h.get('total_pnl_pct', 0)
                print(f"  {h.get('name')}: {close} ({pct:+.2f}%) 总盈亏:{total_pnl:+.2f}%")


if __name__ == '__main__':
    main()
