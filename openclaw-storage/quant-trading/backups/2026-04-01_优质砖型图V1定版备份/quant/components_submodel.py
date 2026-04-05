def classify_components_submodel(industry: str, signal_count: float = 0.0, close: float = 0.0, mf_positive_days_5: float = 0.0, mf_strength: float = 0.0):
    if industry != '元器件':
        return None
    try:
        sc = float(signal_count or 0)
    except Exception:
        sc = 0.0
    try:
        cp = float(close or 0)
    except Exception:
        cp = 0.0
    try:
        mp = float(mf_positive_days_5 or 0)
    except Exception:
        mp = 0.0
    try:
        ms = float(mf_strength or 0)
    except Exception:
        ms = 0.0

    low_quality = ((cp < 10 and mp < 1.5 and ms < -0.002) or (sc >= 150 and mp < 1.6))
    if low_quality:
        return '低质量趋势元器件'
    return '优质趋势元器件'
