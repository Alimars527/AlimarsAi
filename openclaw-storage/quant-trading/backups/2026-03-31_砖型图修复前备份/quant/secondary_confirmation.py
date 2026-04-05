def secondary_confirmation_tier(hkhold_positive: bool, margin_positive: bool, mf_positive_days_5: float = 0.0):
    try:
        mf_days = float(mf_positive_days_5 or 0)
    except Exception:
        mf_days = 0.0

    if margin_positive:
        return 'strong_confirm'
    if hkhold_positive and mf_days >= 3:
        return 'assist_confirm'
    if hkhold_positive:
        return 'front_only'
    return 'none'
