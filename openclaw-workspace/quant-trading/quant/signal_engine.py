"""第二阶段：信号引擎"""

import pandas as pd

from .strategy_rules import RULES
from .moneyflow_policy import moneyflow_policy_for_industry
from .components_quality_filter import is_bad_components_candidate
from .components_submodel import classify_components_submodel
from .hkhold_policy import hkhold_policy_for_industry
from .margin_policy import margin_policy_for_industry


class SignalEngine:
    def __init__(self):
        self.rules = RULES

    def build_feature_row(self, row: pd.Series) -> dict:
        close = row.get('close', 0)
        ma5 = row.get('ma5', 0)
        ma10 = row.get('ma10', 0)
        vol_ratio = row.get('vol_ratio', 0)
        industry_preferred = bool(row.get('preferred_industry', False))
        market_regime = row.get('market_regime', 'neutral')
        industry = row.get('industry', '')
        mf_policy = moneyflow_policy_for_industry(industry)
        hkhold_view = hkhold_policy_for_industry(
            industry,
            row.get('hkhold_ratio', 0),
            row.get('hkhold_ratio_change', 0),
            row.get('hkhold_ratio_positive_5', 0),
        )
        margin_view = margin_policy_for_industry(
            industry,
            row.get('margin_net_buy_5', 0),
            row.get('margin_positive_days_5', 0),
            row.get('margin_rzye_change_5', 0),
        )

        return {
            'preferred_industry': industry_preferred,
            'industry': industry,
            'trend_up': close >= ma5 >= ma10 if ma5 is not None and ma10 is not None else False,
            'trend_turning': close >= ma5 and ma5 < ma10 if ma5 is not None and ma10 is not None else False,
            'strong_vs_market': row.get('pct_chg', 0) > row.get('benchmark_pct_chg', 0),
            'volume_up': vol_ratio >= 1.5 if vol_ratio is not None else False,
            'below_recent_high': row.get('distance_to_high', 999) <= 0.05,
            'market_regime': market_regime,
            'not_weak_market': market_regime != 'weak',
            'close_above_ma10': close >= ma10 if ma10 is not None else False,
            'prefer_flat_open': row.get('prefer_flat_open', True),
            'mf_positive_5': float(row.get('mf_amount_5', 0) or 0) > 0,
            'mf_positive_days_5_ok': float(row.get('mf_positive_days_5', 0) or 0) >= 3,
            'mf_divergence': bool(row.get('mf_divergence', False)),
            'mf_strength_ok': float(row.get('mf_strength', 0) or 0) > -0.02,
            'mf_policy_hard_filter_divergence': mf_policy.get('hard_filter_divergence', False),
            'mf_policy_prefer_positive_days': mf_policy.get('prefer_positive_days', False),
            'mf_policy_prefer_positive_5': mf_policy.get('prefer_positive_5', False),
            'bad_components_candidate': is_bad_components_candidate(
                industry,
                row.get('historical_signal_count', 0),
                row.get('mf_positive_days_5', 0),
                row.get('close', 0),
                row.get('mf_strength', 0),
            ),
            'components_submodel': classify_components_submodel(
                industry,
                row.get('historical_signal_count', 0),
                row.get('close', 0),
                row.get('mf_positive_days_5', 0),
                row.get('mf_strength', 0),
            ),
            'hkhold_score': hkhold_view['hkhold_score'],
            'hkhold_positive': hkhold_view['hkhold_positive'],
            'hkhold_reason': hkhold_view['hkhold_reason'],
            'margin_score': margin_view['margin_score'],
            'margin_positive': margin_view['margin_positive'],
            'margin_reason': margin_view['margin_reason'],
        }

    def evaluate(self, strategy_name: str, row: pd.Series):
        features = self.build_feature_row(row)
        rule = self.rules[strategy_name]
        passed, reason = rule(features)
        return {
            'strategy': strategy_name,
            'passed': passed,
            'reason': '、'.join(reason),
            'features': features,
        }
