import asyncio
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import DATA_DIR, get_settings
from app.connectors.registry import get_connector
from app.db import create_session
from app.services.history import upsert_accounts, upsert_campaigns, upsert_metrics
from app.services.logging_config import get_logger


STATUS_FILE = DATA_DIR / "sync_status.json"


async def sync_platforms(
    db: Session,
    platforms: list[str],
    start_date: date,
    end_date: date,
    account_ids: list[str] | None = None,
    campaign_ids: list[str] | None = None,
    source: str = "manual",
    persist_status: bool = True,
) -> list[dict]:
    logger = get_logger()
    results = []
    account_ids = account_ids or []
    campaign_ids = campaign_ids or []
    for platform in platforms:
        connector = get_connector(platform)
        try:
            accounts = await connector.get_accounts()
            if account_ids:
                accounts = [account for account in accounts if account.id in account_ids]
            upsert_accounts(db, platform, accounts)
            for account in accounts:
                campaigns = await connector.get_campaigns(account.id)
                upsert_campaigns(db, platform, campaigns)
                metrics = await connector.get_metrics(account.id, start_date, end_date, campaign_ids or None)
                upsert_metrics(db, metrics)
                result = {
                    "platform": platform,
                    "account_id": account.id,
                    "campaigns": len(campaigns),
                    "metric_rows": len(metrics),
                }
                logger.info("sync_success source=%s platform=%s account_id=%s campaigns=%s metric_rows=%s", source, platform, account.id, len(campaigns), len(metrics))
                results.append(result)
        except Exception as exc:
            message = str(exc)
            logger.error("sync_error source=%s platform=%s message=%s", source, platform, message)
            results.append({"platform": platform, "error": message})
    if persist_status:
        save_sync_status(source, start_date, end_date, results)
    return results


def save_sync_status(source: str, start_date: date, end_date: date, results: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    has_errors = any("error" in item for item in results)
    payload = {
        "last_run_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": source,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "ok": not has_errors,
        "results": results,
    }
    STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_sync_status() -> dict:
    if not STATUS_FILE.exists():
        return {"last_run_at": None, "ok": None, "results": []}
    return json.loads(STATUS_FILE.read_text(encoding="utf-8"))


def run_scheduled_sync() -> None:
    settings = get_settings()
    end = date.today()
    start = end - timedelta(days=max(settings.auto_sync_period_days, 1) - 1)
    platforms = settings.csv_list(settings.auto_sync_platforms)
    with create_session() as db:
        asyncio.run(sync_platforms(db, platforms, start, end, source="scheduled", persist_status=True))
