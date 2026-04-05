import pandas as pd

from .b1_pattern_features import add_b1_pattern_features
from .b1_perfect_features import add_b1_perfect_features
from .b1_base_features import add_b1_base_features
from .b1_confirmation_features import add_b1_confirmation_features
from .b1_capital_confirmation import add_b1_capital_confirmation
from .b1_context_confirmation import add_b1_context_confirmation
from .b2_pattern_features import add_b2_pattern_features


def _safe_num(v):
    try:
        return float(v)
    except Exception:
        return None


def detect_b1_b2_signals(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    out = df.copy()
    out = add_b1_pattern_features(out)
    out = add_b1_perfect_features(out)
    out = add_b1_base_features(out)
    out = add_b1_confirmation_features(out)
    out = add_b1_capital_confirmation(out)
    out = add_b2_pattern_features(out)
    if 'b1_base_valid' not in out.columns:
        out['b1_base_valid'] = False

    white = pd.to_numeric(out.get('white_line'), errors='coerce') if 'white_line' in out.columns else pd.Series(index=out.index, dtype='float64')
    yellow = pd.to_numeric(out.get('yellow_line'), errors='coerce') if 'yellow_line' in out.columns else pd.Series(index=out.index, dtype='float64')
    dif = pd.to_numeric(out.get('macd_dif'), errors='coerce') if 'macd_dif' in out.columns else pd.Series(index=out.index, dtype='float64')
    jv = pd.to_numeric(out.get('kdj_j'), errors='coerce') if 'kdj_j' in out.columns else pd.Series(index=out.index, dtype='float64')
    pct = pd.to_numeric(out.get('pct_chg'), errors='coerce') if 'pct_chg' in out.columns else pd.Series(index=out.index, dtype='float64')
    vol = pd.to_numeric(out.get('vol'), errors='coerce') if 'vol' in out.columns else pd.Series(index=out.index, dtype='float64')
    prev_vol = vol.shift(1)

    out['b1_dif_positive'] = dif > 0
    out['b1_white_above_yellow'] = white > yellow
    out['b1_j_support'] = jv <= 20
    out['b1_volume_expand'] = vol > prev_vol
    out['b1_price_expand'] = pct > 0

    out['day_b1'] = (
        out['b1_dif_positive'].fillna(False)
        & out['b1_white_above_yellow'].fillna(False)
        & out['b1_volume_expand'].fillna(False)
        & out['b1_price_expand'].fillna(False)
    )
    capital_score = pd.to_numeric(out['b1_confirm_capital_score'], errors='coerce') if 'b1_confirm_capital_score' in out.columns else pd.Series(0, index=out.index, dtype='float64')
    context_score = pd.to_numeric(out['b1_confirm_context_score'], errors='coerce') if 'b1_confirm_context_score' in out.columns else pd.Series(0, index=out.index, dtype='float64')
    out['b1_confirm_capital_pass'] = out['day_b1'].fillna(False) & (capital_score.fillna(0) >= 1)
    out['b1_strong_confirm_capital_pass'] = out['day_b1'].fillna(False) & (capital_score.fillna(0) >= 2)
    out['b1_confirm_context_pass'] = out['day_b1'].fillna(False) & (context_score.fillna(0) >= 1)
    out['b1_strong_confirm_context_pass'] = out['day_b1'].fillna(False) & (context_score.fillna(0) >= 2)
    out['b1_confirm_capital_context_pass'] = out['b1_confirm_capital_pass'].fillna(False) & out['b1_confirm_context_pass'].fillna(False)
    brick_signal = out.get('brick_formula_signal', pd.Series(False, index=out.index)).fillna(False)
    out['b1_confirm_non_brick_pass'] = out['b1_confirm_capital_pass'].fillna(False) & (~brick_signal)
    out['b1_confirm_capital_industry_pass'] = out['b1_confirm_capital_pass'].fillna(False) & out.get('b1_research_industry_pool', pd.Series(False, index=out.index)).fillna(False)
    out['b1_confirm_capital_industry_non_brick_pass'] = out['b1_confirm_capital_industry_pass'].fillna(False) & (~brick_signal)

    body = (pd.to_numeric(out.get('close'), errors='coerce') - pd.to_numeric(out.get('open'), errors='coerce')).abs()
    full_range = (pd.to_numeric(out.get('high'), errors='coerce') - pd.to_numeric(out.get('low'), errors='coerce')).replace(0, pd.NA)
    out['b1_close_not_weak'] = ((body / full_range) > 0.2).fillna(False)

    out['b1_strength'] = 0
    out.loc[out['b1_dif_positive'].fillna(False), 'b1_strength'] += 1
    out.loc[out['b1_white_above_yellow'].fillna(False), 'b1_strength'] += 1
    out.loc[out['b1_volume_expand'].fillna(False), 'b1_strength'] += 1
    out.loc[out['b1_price_expand'].fillna(False), 'b1_strength'] += 1
    out.loc[out['b1_j_support'].fillna(False), 'b1_strength'] += 1
    out.loc[out['b1_close_not_weak'].fillna(False), 'b1_strength'] += 1

    out['b1_confirm_volume'] = out['b1_volume_expand'].fillna(False)
    out['b1_confirm_close_quality'] = out['b1_close_not_weak'].fillna(False)
    out['b1_confirm_structure'] = out['b1_white_above_yellow'].fillna(False)
    out['b1_confirm_followthrough'] = (
        out['b1_price_expand'].fillna(False)
        & (pct >= 2).fillna(False)
        & out['b1_close_not_weak'].fillna(False)
    )
    out['b1_confirm_base'] = out['b1_base_valid'].fillna(False)

    out['b1_confirm_score'] = 0
    for col in [
        'b1_confirm_volume',
        'b1_confirm_close_quality',
        'b1_confirm_structure',
        'b1_confirm_followthrough',
        'b1_confirm_base',
    ]:
        out.loc[out[col].fillna(False), 'b1_confirm_score'] += 1

    out['b1_confirm_pass'] = out['day_b1'].fillna(False) & (out['b1_confirm_score'] >= 3)
    out['b1_strong_confirm_pass'] = out['day_b1'].fillna(False) & (out['b1_confirm_score'] >= 4)

    out['perfect_b1'] = (
        out['day_b1'].fillna(False)
        & out['b1_j_support'].fillna(False)
        & out['b1_close_not_weak'].fillna(False)
        & out['b1_rise_on_volume'].fillna(False)
        & out['b1_white_not_broken'].fillna(False)
        & out['b1_perfect_proxy'].fillna(False)
        & (out['b1_strength'] >= 5)
    )
    out['standard_b1'] = (
        out['day_b1'].fillna(False)
        & (~out['perfect_b1'].fillna(False))
        & out['b1_standard_proxy'].fillna(False)
        & (out['b1_strength'] >= 4)
    )
    out['weak_b1'] = (
        out['day_b1'].fillna(False)
        & (~out['perfect_b1'].fillna(False))
        & (~out['standard_b1'].fillna(False))
    )

    out['b1_base_for_b2'] = (
        out['day_b1'].fillna(False)
        & (~out['perfect_b1'].fillna(False))
        & (~out['standard_b1'].fillna(False))
        & out['b1_base_valid'].fillna(False)
        & (out['b1_strength'] >= 5)
        & (pct >= 4)
        & (pct <= 6.5)
        & (~out.get('brick_formula_signal', pd.Series(False, index=out.index)).fillna(False))
    )

    out['true_weak_b1'] = (
        out['weak_b1'].fillna(False)
        & (~out['b1_base_for_b2'].fillna(False))
    )

    out['b2_signal'] = (
        out['b2_shape_ready'].fillna(False)
        | (
            out['day_b1'].fillna(False)
            & (pct > 4).fillna(False)
            & (vol >= prev_vol * 1.5).fillna(False)
        )
    )
    out['b2_strength'] = pd.to_numeric(out.get('b2_shape_strength', 0), errors='coerce').fillna(0)
    out.loc[out['b2_signal'].fillna(False) & (out['b2_strength'] < 1), 'b2_strength'] = 1
    boost_mask = (pct > 4).fillna(False) & (vol >= prev_vol * 2).fillna(False) & out['b2_short_upper_shadow'].fillna(False)
    out.loc[boost_mask, 'b2_strength'] = out.loc[boost_mask, 'b2_strength'].clip(lower=2)

    out['week_b1'] = False
    return out
