def compute_derived_metrics(impressions: int, clicks: int, spend: float, conversions: float, conversion_value: float) -> dict:
    ctr = (clicks / impressions) * 100 if impressions else 0.0
    cpc = spend / clicks if clicks else 0.0
    cost_per_conversion = spend / conversions if conversions else 0.0
    roas = conversion_value / spend if spend else 0.0
    return {
        "ctr": round(ctr, 2),
        "cpc": round(cpc, 2),
        "cost_per_conversion": round(cost_per_conversion, 2),
        "roas": round(roas, 2),
    }
