FOCUS_THEME_MAP = {
    '大科技龙头': ['半导体', '元器件', 'IT设备', '通信设备', '软件服务'],
    '新消费龙头': ['食品', '乳制品', '家用电器', '百货', '超市连锁', '白酒', '啤酒'],
    '新能源车': ['新能源车', '汽车整车', '汽车配件', '电气设备'],
    '白酒': ['白酒', '红黄酒'],
    '创新药': ['生物制药', '化学制药', '医疗保健', '医药商业', '中成药'],
    '固态电池': ['电气设备', '新能源车', '专用机械', '元器件'],
    '券商': ['证券', '多元金融'],
    '稳定币（国家认可方向）': ['证券', '软件服务', '互联网', 'IT设备'],
}


def themes_for_industry(industry: str):
    if not industry:
        return []
    out = []
    for theme, industries in FOCUS_THEME_MAP.items():
        if industry in industries:
            out.append(theme)
    return out
