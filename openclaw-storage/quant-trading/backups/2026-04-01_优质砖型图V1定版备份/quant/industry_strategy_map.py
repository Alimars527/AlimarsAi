"""第二阶段：行业 -> 优先策略映射（第一版）"""

INDUSTRY_STRATEGY_MAP = {
    '元器件': {
        'preferred_strategy': '主线趋势',
        'note': '更适合趋势延续、平开承接、避免高开追。',
    },
    '电气设备': {
        'preferred_strategy': '主线趋势',
        'note': '更适合趋势跟随，重点看强势延续和执行纪律。',
    },
    '软件服务': {
        'preferred_strategy': '主线趋势',
        'note': '可归入主线趋势，但需注意票性分化较大。',
    },
    '医药商业': {
        'preferred_strategy': '轮动补涨',
        'note': '不适合主线持有，更适合轮动短打+纪律化退出。',
    },
    '化学制药': {
        'preferred_strategy': '轮动补涨',
        'note': '不适合粗暴主线趋势持有，更适合轮动补涨。',
    },
}


def preferred_strategy_for_industry(industry: str):
    item = INDUSTRY_STRATEGY_MAP.get(industry)
    if not item:
        return None
    return item.get('preferred_strategy')
