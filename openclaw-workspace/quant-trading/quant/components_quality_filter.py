def is_bad_components_candidate(industry: str, signal_count: int = 0, mf_positive_days_5: float = 0.0, close: float = 0.0, mf_strength: float = 0.0):
    if industry != '元器件':
        return False
    try:
        sc = float(signal_count or 0)
    except Exception:
        sc = 0.0
    try:
        mp = float(mf_positive_days_5 or 0)
    except Exception:
        mp = 0.0
    try:
        cp = float(close or 0)
    except Exception:
        cp = 0.0
    try:
        ms = float(mf_strength or 0)
    except Exception:
        ms = 0.0

    # v2：更贴近当前跑出来的坏票画像
    low_price_weak_flow = cp < 10 and mp < 1.5 and ms < -0.002
    noisy_signal_low_quality = sc >= 150 and mp < 1.6 and ms < -0.0015
    return low_price_weak_flow or noisy_signal_low_quality
