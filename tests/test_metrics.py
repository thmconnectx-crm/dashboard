from app.services.metrics import compute_derived_metrics


def test_compute_derived_metrics():
    metrics = compute_derived_metrics(
        impressions=1000,
        clicks=100,
        spend=250.0,
        conversions=10,
        conversion_value=1000.0,
    )

    assert metrics["ctr"] == 10.0
    assert metrics["cpc"] == 2.5
    assert metrics["cost_per_conversion"] == 25.0
    assert metrics["roas"] == 4.0


def test_compute_derived_metrics_avoids_division_by_zero():
    metrics = compute_derived_metrics(
        impressions=0,
        clicks=0,
        spend=0,
        conversions=0,
        conversion_value=0,
    )

    assert metrics == {"ctr": 0.0, "cpc": 0.0, "cost_per_conversion": 0.0, "roas": 0.0}
