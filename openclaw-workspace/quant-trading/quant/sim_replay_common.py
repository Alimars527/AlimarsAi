from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


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


def load_universe(data_dir: Optional[Path] = None) -> pd.DataFrame:
    data_dir = Path(data_dir) if data_dir else DATA
    meta = pd.read_csv(data_dir / "meta" / "stock_basic.csv", dtype=str).fillna("")
    meta = meta[~meta["ts_code"].str.endswith(".BJ")]
    meta = meta[~meta["name"].str.upper().str.contains("ST", na=False)]
    meta = meta[~meta["industry"].str.contains("房地产", na=False)]
    meta = meta[meta["industry"] != "银行"]
    meta = meta[~meta["ts_code"].str.startswith("300")]
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
