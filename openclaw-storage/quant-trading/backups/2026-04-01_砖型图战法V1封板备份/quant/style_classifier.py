"""第二阶段：主线趋势内部票性分层（第二版）"""


def classify_trend_style(row):
    vol_ratio = float(row.get('vol_ratio', 0) or 0)
    pct_chg = float(row.get('pct_chg', 0) or 0)
    distance_to_high = float(row.get('distance_to_high', 999) or 999)
    vol10 = float(row.get('volatility_10', 0) or 0)
    strength_days = float(row.get('strong_days_10', 0) or 0)

    # 高弹性主线：放量较明显 + 波动偏大 + 接近高位 + 近期持续偏强
    if vol_ratio >= 1.35 and abs(pct_chg) >= 2.0 and distance_to_high <= 0.1 and vol10 >= 0.035 and strength_days >= 4:
        return '高弹性主线'

    # 稳定趋势主线：趋势完整、接近高位、近期持续偏强，但波动不极端
    if vol_ratio >= 1.0 and distance_to_high <= 0.12 and strength_days >= 5 and vol10 < 0.05:
        return '稳定趋势主线'

    return '边缘趋势'
