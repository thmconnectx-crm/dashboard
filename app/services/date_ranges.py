from datetime import date, timedelta


def resolve_period(period: str, start_date: str | None = None, end_date: str | None = None) -> tuple[date, date]:
    today = date.today()
    if period == "last_7":
        return today - timedelta(days=6), today
    if period == "last_30":
        return today - timedelta(days=29), today
    if period == "last_90":
        return today - timedelta(days=89), today
    if period == "month_to_date":
        return today.replace(day=1), today
    if period == "custom" and start_date and end_date:
        return date.fromisoformat(start_date), date.fromisoformat(end_date)
    return today - timedelta(days=29), today
