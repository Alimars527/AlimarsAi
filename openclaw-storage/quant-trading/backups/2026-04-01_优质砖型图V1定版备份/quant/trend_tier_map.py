"""第二阶段：主线趋势两层票性模型（阶段版）"""


def normalize_trend_tier(dominant_style: str):
    if dominant_style == '稳定趋势主线':
        return '主线趋势-优先'
    return '主线趋势-谨慎'
