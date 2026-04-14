from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


# ── V4 硬黑名单 ──────────────────────────────────────
# 基于V3历史回测诊断，排除长期系统性亏损的10个行业。
# 来源: sim_replay_20230101_brick_v4_hard_filter (251.79% vs V3 101.64%)
V4_EXCLUDED_INDUSTRIES: set[str] = {
    '航空',       # 16 trades, PnL=-11,849, WR=43.8%
    '电气设备',   # 16 trades, PnL=-7,985
    '旅游服务',   # 5 trades, PnL=-7,805 (全亏)
    '黄金',       # 17 trades, PnL=-7,730
    '全国地产',   # 4 trades, PnL=-7,455, WR=0%
    '轻工机械',   # PnL≈-6,000
    '农药化肥',   # PnL≈-5,000
    '石油贸易',   # PnL≈-4,800
    '矿物制品',   # PnL≈-4,400
    '专用机械',   # PnL≈-4,400
}


def _default_cache_dir(data_dir: Path) -> Path:
    return data_dir / "cache" / "sim_replay_prepared"


def _cache_path(code: str, start_date: str, end_date: str, cache_dir: Path) -> Path:
    return cache_dir / f"{code}_{start_date}_{end_date}.pkl"


def _cache_is_fresh(cache_path: Path, dependency_paths: list[Path]) -> bool:
    if not cache_path.exists():
        return False
    try:
        cache_mtime = cache_path.stat().st_mtime
    except OSError:
        return False
    for dep in dependency_paths:
        try:
            if dep.exists() and dep.stat().st_mtime > cache_mtime:
                return False
        except OSError:
            return False
    return True


def safe_num(v):
    return pd.to_numeric(v, errors="coerce")


def load_omav(data_dir: Optional[Path] = None) -> pd.DataFrame:
    data_dir = Path(data_dir) if data_dir else DATA
    path = data_dir / "omav" / "omav_daily_standardized_20260402.csv"
    df = pd.read_csv(path, dtype={"trade_date": str})
    df = df.sort_values("trade_date").reset_index(drop=True)
    if "omav_rotation_warning_flag" not in df.columns:
        df["omav_rotation_warning_flag"] = safe_num(df.get("omav_value")).fillna(0) <= -2.3
    if "omav_bear_regime_flag" not in df.columns:
        if "omav_5day_sum" in df.columns:
            df["omav_bear_regime_flag"] = safe_num(df["omav_5day_sum"]).fillna(0) < -5
        else:
            v = safe_num(df.get("omav_value")).fillna(0)
            df["omav_bear_regime_flag"] = v.rolling(5).sum() < -5
    return df


def load_trade_calendar(start_date: str, end_date: str, data_dir: Optional[Path] = None) -> list[str]:
    data_dir = Path(data_dir) if data_dir else DATA
    cal = pd.read_csv(data_dir / "daily" / "000001.SZ.csv", dtype={"trade_date": str})[["trade_date"]]
    cal = cal.drop_duplicates().sort_values("trade_date")
    return [d for d in cal["trade_date"].tolist() if start_date <= d <= end_date]


def load_universe(
    data_dir: Optional[Path] = None,
    excluded_industries: Optional[set[str]] = None,
) -> pd.DataFrame:
    """加载股票池。

    Args:
        data_dir: 数据目录，默认 DATA。
        excluded_industries: 额外排除的行业集合（V4黑名单等），默认不排除。
    """
    data_dir = Path(data_dir) if data_dir else DATA
    meta = pd.read_csv(data_dir / "meta" / "stock_basic.csv", dtype=str).fillna("")
    meta = meta[~meta["ts_code"].str.endswith(".BJ")]
    meta = meta[~meta["name"].str.upper().str.contains("ST", na=False)]
    meta = meta[~meta["industry"].str.contains("房地产", na=False)]
    meta = meta[meta["industry"] != "银行"]
    meta = meta[~meta["ts_code"].str.startswith("300")]
    if excluded_industries:
        meta = meta[~meta["industry"].isin(excluded_industries)]
    return meta[["ts_code", "name", "industry", "list_date"]].copy()


def prepare_code_df(
    code: str,
    start_date: str,
    end_date: str,
    data_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
) -> Optional[pd.DataFrame]:
    from quant.indicators import add_tactic_base_indicators
    from quant.brick_formula import add_brick_formula_flags

    data_dir = Path(data_dir) if data_dir else DATA
    p_daily = data_dir / "daily" / f"{code}.csv"
    p_basic = data_dir / "daily_basic" / f"{code}.csv"
    if not p_daily.exists() or not p_basic.exists():
        return None

    cache_dir = Path(cache_dir) if cache_dir else _default_cache_dir(data_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_path(code, start_date, end_date, cache_dir)
    dependency_paths = [
        p_daily,
        p_basic,
        ROOT / "quant" / "indicators.py",
        ROOT / "quant" / "brick_formula.py",
        Path(__file__),
    ]
    if _cache_is_fresh(cache_path, dependency_paths):
        try:
            cached = pd.read_pickle(cache_path)
            if isinstance(cached, pd.DataFrame) and not cached.empty:
                return cached.reset_index(drop=True)
        except Exception:
            pass

    try:
        d = pd.read_csv(p_daily, dtype={"trade_date": str}).sort_values("trade_date").reset_index(drop=True)
        b = pd.read_csv(p_basic, dtype={"trade_date": str})
        if d.empty or "trade_date" not in d.columns:
            return None

        for c in ["open", "high", "low", "close", "vol", "pct_chg"]:
            if c in d.columns:
                d[c] = safe_num(d[c])

        if "total_mv" in b.columns:
            b = b[["trade_date", "total_mv"]].copy()
            b["total_mv_billion"] = safe_num(b["total_mv"]) / 10000.0
            d = d.merge(b[["trade_date", "total_mv_billion"]], on="trade_date", how="left")
        else:
            d["total_mv_billion"] = pd.NA

        d = add_tactic_base_indicators(d)
        d = add_brick_formula_flags(d)

        for c in ["brick_formula_green", "brick_raw_turn_red", "brick_history_ok"]:
            if c not in d.columns:
                d[c] = False
        if "brick_formula_value" not in d.columns:
            d["brick_formula_value"] = 0.0

        d = d[(d["trade_date"] >= start_date) & (d["trade_date"] <= end_date)].copy()
        if d.empty:
            return None
        d = d.reset_index(drop=True)
        try:
            d.to_pickle(cache_path)
        except Exception:
            pass
        return d
    except Exception:
        return None


def build_prepared_universe(
    start_date: str,
    end_date: str,
    data_dir: Optional[Path] = None,
    min_rows: int = 40,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    excluded_industries: Optional[set[str]] = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, dict[str, int]], dict[tuple[str, str], bool]]:
    data_dir = Path(data_dir) if data_dir else DATA
    meta = load_universe(data_dir, excluded_industries=excluded_industries)

    code_data: dict[str, pd.DataFrame] = {}
    code_idx: dict[str, dict[str, int]] = {}
    industry_daily_ret_rows = []

    total = len(meta)
    for i, r in enumerate(meta.itertuples(index=False), start=1):
        c = r.ts_code
        df = prepare_code_df(c, start_date, end_date, data_dir)
        if df is not None and len(df) >= min_rows:
            code_data[c] = df
            code_idx[c] = {td: j for j, td in enumerate(df["trade_date"].tolist())}
            t = df[["trade_date", "pct_chg"]].copy()
            t["industry"] = r.industry
            industry_daily_ret_rows.append(t)
        if progress_cb:
            progress_cb(i, total)

    if industry_daily_ret_rows:
        ind_df = pd.concat(industry_daily_ret_rows, ignore_index=True)
        ind_df["pct_chg"] = safe_num(ind_df["pct_chg"])
        board = (
            ind_df.groupby(["trade_date", "industry"], as_index=False)["pct_chg"]
            .mean()
            .sort_values(["trade_date", "pct_chg"], ascending=[True, False])
        )
        board["rank"] = board.groupby("trade_date")["pct_chg"].rank(method="first", ascending=False)
        board_top5 = board[board["rank"] <= 5].copy()
        rotation_map = board_top5.assign(flag=True).set_index(["trade_date", "industry"])["flag"].to_dict()
    else:
        rotation_map = {}

    return meta, code_data, code_idx, rotation_map
