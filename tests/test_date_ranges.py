from datetime import date

from app.services.date_ranges import resolve_period


def test_custom_period():
    start, end = resolve_period("custom", "2026-07-01", "2026-07-10")

    assert start == date(2026, 7, 1)
    assert end == date(2026, 7, 10)


def test_default_period_is_valid_range():
    start, end = resolve_period("unknown")

    assert start <= end
    assert (end - start).days == 29
