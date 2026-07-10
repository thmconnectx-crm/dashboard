from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.services.logging_config import get_logger
from app.services.sync import run_scheduled_sync


_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    settings = get_settings()
    if not settings.auto_sync_enabled:
        return
    if _scheduler and _scheduler.running:
        return
    hour, minute = _parse_time(settings.auto_sync_time)
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(run_scheduled_sync, "cron", hour=hour, minute=minute, id="daily_ads_sync", replace_existing=True)
    _scheduler.start()
    get_logger().info("scheduler_started auto_sync_time=%s platforms=%s", settings.auto_sync_time, settings.auto_sync_platforms)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        get_logger().info("scheduler_stopped")


def _parse_time(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = max(0, min(23, int(hour_text)))
        minute = max(0, min(59, int(minute_text)))
        return hour, minute
    except Exception:
        return 3, 0
