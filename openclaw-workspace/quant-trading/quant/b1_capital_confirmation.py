import pandas as pd


def add_b1_capital_confirmation(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    out = df.copy()

    margin_net_buy = pd.to_numeric(out.get('margin_net_buy'), errors='coerce') if 'margin_net_buy' in out.columns else pd.Series(0, index=out.index, dtype='float64')
    margin_positive_days_5 = pd.to_numeric(out.get('margin_positive_days_5'), errors='coerce') if 'margin_positive_days_5' in out.columns else pd.Series(0, index=out.index, dtype='float64')
    margin_rzye_change = pd.to_numeric(out.get('margin_rzye_change'), errors='coerce') if 'margin_rzye_change' in out.columns else pd.Series(0, index=out.index, dtype='float64')

    mf_amount_5 = pd.to_numeric(out.get('mf_amount_5'), errors='coerce') if 'mf_amount_5' in out.columns else pd.Series(0, index=out.index, dtype='float64')
    mf_positive_days_5 = pd.to_numeric(out.get('mf_positive_days_5'), errors='coerce') if 'mf_positive_days_5' in out.columns else pd.Series(0, index=out.index, dtype='float64')
    mf_strength = pd.to_numeric(out.get('mf_strength'), errors='coerce') if 'mf_strength' in out.columns else pd.Series(0, index=out.index, dtype='float64')
    mf_divergence = out.get('mf_divergence', pd.Series(False, index=out.index)).fillna(False)

    hkhold_ratio_change = pd.to_numeric(out.get('hkhold_ratio_change'), errors='coerce') if 'hkhold_ratio_change' in out.columns else pd.Series(0, index=out.index, dtype='float64')
    hkhold_ratio_trend_up = out.get('hkhold_ratio_trend_up', pd.Series(False, index=out.index)).fillna(False)
    hkhold_ratio_positive_5 = pd.to_numeric(out.get('hkhold_ratio_positive_5'), errors='coerce') if 'hkhold_ratio_positive_5' in out.columns else pd.Series(0, index=out.index, dtype='float64')

    out['b1_confirm_margin'] = (
        ((margin_net_buy > 0).fillna(False) & (margin_positive_days_5 >= 2).fillna(False))
        | (margin_rzye_change > 0).fillna(False)
    )
    out['b1_confirm_moneyflow'] = (
        ((mf_amount_5 > 0).fillna(False) & (mf_positive_days_5 >= 2).fillna(False))
        | ((mf_strength > 0).fillna(False) & (~mf_divergence))
    )
    out['b1_confirm_hkhold'] = (
        (hkhold_ratio_change > 0).fillna(False)
        | hkhold_ratio_trend_up
        | (hkhold_ratio_positive_5 >= 2).fillna(False)
    )

    out['b1_confirm_capital_score'] = 0
    out.loc[out['b1_confirm_margin'].fillna(False), 'b1_confirm_capital_score'] += 2
    out.loc[out['b1_confirm_moneyflow'].fillna(False), 'b1_confirm_capital_score'] += 1
    out.loc[out['b1_confirm_hkhold'].fillna(False), 'b1_confirm_capital_score'] += 1

    out['b1_confirm_capital_pass'] = False
    out['b1_strong_confirm_capital_pass'] = False
    return out
