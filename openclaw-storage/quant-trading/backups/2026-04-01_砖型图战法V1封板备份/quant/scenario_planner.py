def build_scenarios(close: float, support: float, pressure: float):
    if not close or support is None or pressure is None:
        return {
            'high_open': '数据不足',
            'flat_open': '数据不足',
            'low_open': '数据不足',
        }

    high_open = (
        f'若高开并快速站上 {round(close * 1.01, 2)}，观察是否放量冲击 {pressure:.2f}；'
        f'若高开过多但量能不够，谨慎追高。'
    )
    flat_open = (
        f'若平开附近震荡，重点看 {support:.2f} 一带承接；'
        f'守住则按原计划持有/低吸，向上看 {pressure:.2f}。'
    )
    low_open = (
        f'若低开靠近 {support:.2f}，先看是否止跌企稳；'
        f'若直接跌破关键支撑并无法收回，则转谨慎。'
    )
    return {
        'high_open': high_open,
        'flat_open': flat_open,
        'low_open': low_open,
    }
