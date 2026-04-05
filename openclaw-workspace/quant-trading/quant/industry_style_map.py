INDUSTRY_STYLE_MAP = {
    # 成长趋势类
    '元器件': 'growth_trend',
    '电气设备': 'growth_trend',
    '半导体': 'growth_trend',
    'IT设备': 'growth_trend',
    '软件服务': 'growth_trend',
    '通信设备': 'growth_trend',
    '电器仪表': 'growth_trend',
    '机械基件': 'growth_trend',
    '专用机械': 'growth_trend',
    '工程机械': 'growth_trend',
    '机床制造': 'growth_trend',
    '农用机械': 'growth_trend',
    '运输设备': 'growth_trend',
    '航空': 'growth_trend',
    '汽车整车': 'growth_trend',
    '汽车配件': 'growth_trend',
    '新型电力': 'growth_trend',

    # 防守轮动类
    '水力发电': 'defensive_rotation',
    '火力发电': 'defensive_rotation',
    '供气供热': 'defensive_rotation',
    '港口': 'defensive_rotation',
    '公路': 'defensive_rotation',
    '路桥': 'defensive_rotation',
    '公共交通': 'defensive_rotation',
    '仓储物流': 'defensive_rotation',
    '水运': 'defensive_rotation',
    '水务': 'defensive_rotation',
    '环境保护': 'defensive_rotation',

    # 稳态消费类
    '白酒': 'steady_consumer',
    '啤酒': 'steady_consumer',
    '食品': 'steady_consumer',
    '乳制品': 'steady_consumer',
    '家用电器': 'steady_consumer',
    '家居用品': 'steady_consumer',
    '旅游景点': 'steady_consumer',
    '酒店餐饮': 'steady_consumer',
    '百货': 'steady_consumer',
    '服饰': 'steady_consumer',
    '日用化工': 'steady_consumer',
    '文教休闲': 'steady_consumer',
    '出版业': 'steady_consumer',
    '影视音像': 'steady_consumer',
    '商贸代理': 'steady_consumer',

    # 周期资源类
    '石油开采': 'cyclical_resource',
    '石油加工': 'cyclical_resource',
    '石油贸易': 'cyclical_resource',
    '煤炭开采': 'cyclical_resource',
    '煤炭加工': 'cyclical_resource',
    '有色': 'cyclical_resource',
    '小金属': 'cyclical_resource',
    '化工原料': 'cyclical_resource',
    '化纤': 'cyclical_resource',
    '化工机械': 'cyclical_resource',
    '农药化肥': 'cyclical_resource',
    '钢加工': 'cyclical_resource',
    '普钢': 'cyclical_resource',
    '铜': 'cyclical_resource',
    '铝': 'cyclical_resource',
    '铅锌': 'cyclical_resource',
    '塑料': 'cyclical_resource',
    '橡胶': 'cyclical_resource',
    '玻璃': 'cyclical_resource',
    '水泥': 'cyclical_resource',
    '矿物制品': 'cyclical_resource',
    '染料涂料': 'cyclical_resource',

    # 高弹性主题类
    '光伏设备': 'high_beta_theme',
    '新能源车': 'high_beta_theme',
    '互联网': 'high_beta_theme',
    '广告包装': 'high_beta_theme',
    '综合类': 'high_beta_theme',
    '种植业': 'high_beta_theme',
    '农业综合': 'high_beta_theme',
    '饲料': 'high_beta_theme',

    # 医药保守成长类
    '中成药': 'medical_stable_growth',
    '化学制药': 'medical_stable_growth',
    '医疗保健': 'medical_stable_growth',
    '医药商业': 'medical_stable_growth',
    '生物制药': 'medical_stable_growth',

    # 金融地产独立类（先单独归口，后续可再拆）
    '证券': 'financial_property',
    '银行': 'financial_property',
    '保险': 'financial_property',
    '多元金融': 'financial_property',
    '区域地产': 'financial_property',
    '全国地产': 'financial_property',
    '园区开发': 'financial_property',
    '房产服务': 'financial_property',

    # 基建建材类
    '建筑工程': 'infrastructure_material',
    '装修装饰': 'infrastructure_material',
    '其他建材': 'infrastructure_material',
    '陶瓷': 'infrastructure_material',
    '造纸': 'infrastructure_material',

    # 其余尾部行业继续归口
    '纺织': 'steady_consumer',
    '红黄酒': 'steady_consumer',
    '软饮料': 'steady_consumer',
    '超市连锁': 'steady_consumer',
    '旅游服务': 'steady_consumer',
    '电器连锁': 'steady_consumer',
    '其他商业': 'steady_consumer',
    '批发业': 'steady_consumer',

    '摩托车': 'growth_trend',
    '纺织机械': 'growth_trend',
    '船舶': 'growth_trend',
    '汽车服务': 'growth_trend',
    '轻工机械': 'growth_trend',
    '电信运营': 'growth_trend',

    '黄金': 'cyclical_resource',
    '特种钢': 'cyclical_resource',
    '焦炭加工': 'cyclical_resource',

    '空运': 'defensive_rotation',
    '铁路': 'defensive_rotation',
    '机场': 'defensive_rotation',
    '渔业': 'defensive_rotation',
    '林业': 'defensive_rotation',
    '商品城': 'defensive_rotation',
}


def classify_industry_style(industry: str) -> str:
    if not industry:
        return 'unclassified'
    return INDUSTRY_STYLE_MAP.get(industry, 'unclassified')
