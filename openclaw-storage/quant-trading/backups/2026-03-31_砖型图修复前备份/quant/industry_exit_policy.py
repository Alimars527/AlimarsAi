def industry_exit_overrides(industry: str, open_scenario: str = 'flat_open'):
    industry = industry or ''

    if industry == '软件服务':
        base = {
            'take_profit_pct': 0.022,
            'stop_loss_pct': -0.018,
            'max_hold_days': 1,
            'exit_on_weak_close': True,
            'early_exit_on_red_day': True,
        }
        if open_scenario == 'high_open':
            base.update({'take_profit_pct': 0.015, 'max_hold_days': 1})
        elif open_scenario == 'low_open':
            base.update({'take_profit_pct': 0.018, 'stop_loss_pct': -0.016, 'max_hold_days': 1, 'early_exit_on_red_day': True})
        return base

    if industry == '电气设备':
        base = {
            'take_profit_pct': 0.028,
            'stop_loss_pct': -0.02,
            'max_hold_days': 1,
            'exit_on_weak_close': True,
            'early_exit_on_red_day': True,
        }
        if open_scenario == 'high_open':
            base.update({'take_profit_pct': 0.018, 'max_hold_days': 1})
        elif open_scenario == 'low_open':
            base.update({'take_profit_pct': 0.022, 'stop_loss_pct': -0.018, 'max_hold_days': 1})
        return base

    if industry == '元器件':
        base = {
            'take_profit_pct': 0.03,
            'stop_loss_pct': -0.022,
            'max_hold_days': 1,
            'exit_on_weak_close': True,
            'early_exit_on_red_day': True,
        }
        if open_scenario == 'high_open':
            base.update({'take_profit_pct': 0.018, 'max_hold_days': 1})
        elif open_scenario == 'low_open':
            base.update({'take_profit_pct': 0.022, 'stop_loss_pct': -0.018, 'max_hold_days': 1})
        return base

    return {}
