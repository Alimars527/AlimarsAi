import pandas as pd


def add_b1_context_confirmation(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    out = df.copy()
    industry = out.get('industry', pd.Series('', index=out.index)).fillna('')
    trend_style = out.get('trend_style', pd.Series('', index=out.index)).fillna('')
    preferred_industry = out.get('preferred_industry', pd.Series(False, index=out.index)).fillna(False)

    style_text = trend_style.astype(str)
    industry_text = industry.astype(str)

    out['b1_confirm_style_fit'] = style_text.str.contains('mainline|主线|repair|趋势', case=False, regex=True, na=False)
    out['b1_confirm_industry_fit'] = (
        preferred_industry.astype(bool)
        | industry_text.str.contains('元器件|半导体|电气设备|软件服务|专用机械|通信设备', na=False)
    )
    out['b1_research_industry_pool'] = industry_text.str.contains('电气设备|元器件|软件服务|半导体|专用机械|通信设备', na=False)

    out['b1_confirm_context_score'] = 0
    out.loc[out['b1_confirm_style_fit'].fillna(False), 'b1_confirm_context_score'] += 1
    out.loc[out['b1_confirm_industry_fit'].fillna(False), 'b1_confirm_context_score'] += 1

    out['b1_confirm_context_pass'] = False
    out['b1_strong_confirm_context_pass'] = False
    return out
