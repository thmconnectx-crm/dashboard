from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.connectors.registry import get_connector, get_connectors
from app.db import get_db
from app.exporters import build_excel, build_pdf
from app.schemas import SyncRequest
from app.services.date_ranges import resolve_period
from app.services.history import (
    list_saved_accounts,
    list_saved_campaigns,
    query_metrics,
    upsert_accounts,
    upsert_campaigns,
)
from app.services.metrics import compute_derived_metrics
from app.services.sync import read_sync_status, sync_platforms


router = APIRouter(prefix="/api", tags=["api"])


@router.get("/platforms")
def platforms() -> dict:
    return {
        "items": [
            {"id": platform, "name": "Google Ads" if platform == "google" else "Meta Ads", "configured": connector.is_configured()}
            for platform, connector in get_connectors().items()
        ]
    }


@router.post("/sync")
async def sync_data(payload: SyncRequest, db: Session = Depends(get_db)) -> dict:
    results = await sync_platforms(db, payload.platforms, payload.start_date, payload.end_date, payload.account_ids, payload.campaign_ids)
    return {"items": results}


@router.get("/sync/status")
def sync_status() -> dict:
    return read_sync_status()


@router.post("/accounts/refresh")
async def refresh_accounts(platform: str = Query(...), db: Session = Depends(get_db)) -> dict:
    connector = get_connector(platform)
    try:
        accounts = await connector.get_accounts()
        upsert_accounts(db, platform, accounts)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": [{"platform": platform, "id": account.id, "name": account.name, "currency": account.currency} for account in accounts]}


@router.post("/campaigns/refresh")
async def refresh_campaigns(platform: str = Query(...), account_id: str = Query(...), db: Session = Depends(get_db)) -> dict:
    connector = get_connector(platform)
    try:
        campaigns = await connector.get_campaigns(account_id)
        upsert_campaigns(db, platform, campaigns)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "items": [
            {"platform": platform, "account_id": campaign.account_id, "id": campaign.id, "name": campaign.name, "status": campaign.status}
            for campaign in campaigns
        ]
    }


@router.get("/accounts")
def accounts(platform: str | None = None, db: Session = Depends(get_db)) -> dict:
    return {
        "items": [
            {
                "platform": row.platform,
                "id": row.external_id,
                "name": row.name,
                "currency": row.currency,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in list_saved_accounts(db, platform)
        ]
    }


@router.get("/campaigns")
def campaigns(platform: str | None = None, account_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    return {
        "items": [
            {
                "platform": row.platform,
                "account_id": row.account_id,
                "id": row.external_id,
                "name": row.name,
                "status": row.status,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in list_saved_campaigns(db, platform, account_id)
        ]
    }


@router.get("/dashboard")
def dashboard(
    period: str = Query("last_30"),
    start_date: str | None = None,
    end_date: str | None = None,
    platforms: str = "",
    account_ids: str = "",
    campaign_ids: str = "",
    db: Session = Depends(get_db),
) -> dict:
    start, end = resolve_period(period, start_date, end_date)
    rows = query_metrics(
        db,
        start,
        end,
        [item for item in platforms.split(",") if item] or None,
        [item for item in account_ids.split(",") if item] or None,
        [item for item in campaign_ids.split(",") if item] or None,
    )
    return {
        "range": {"start_date": start.isoformat(), "end_date": end.isoformat()},
        "summary": _aggregate_metric_rows(rows),
        "daily": _aggregate_metric_rows(rows, by_day=True),
    }


@router.get("/metrics")
def metrics(
    start_date: date,
    end_date: date,
    platforms: str = "",
    account_ids: str = "",
    campaign_ids: str = "",
    db: Session = Depends(get_db),
) -> dict:
    rows = query_metrics(
        db,
        start_date,
        end_date,
        [item for item in platforms.split(",") if item] or None,
        [item for item in account_ids.split(",") if item] or None,
        [item for item in campaign_ids.split(",") if item] or None,
    )
    return {"items": [_metric_to_dict(row) for row in rows]}


@router.get("/export/{file_type}")
def export_report(
    file_type: str,
    start_date: date,
    end_date: date,
    platforms: str = "",
    account_ids: str = "",
    campaign_ids: str = "",
    db: Session = Depends(get_db),
):
    rows = query_metrics(
        db,
        start_date,
        end_date,
        [item for item in platforms.split(",") if item] or None,
        [item for item in account_ids.split(",") if item] or None,
        [item for item in campaign_ids.split(",") if item] or None,
    )
    if file_type == "xlsx":
        content = build_excel(rows)
        return Response(
            content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="relatorio-trafego-pago.xlsx"'},
        )
    if file_type == "pdf":
        content = build_pdf(rows, start_date=start_date, end_date=end_date)
        return Response(
            content,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="relatorio-trafego-pago.pdf"'},
        )
    raise HTTPException(status_code=404, detail="Formato nao suportado. Use pdf ou xlsx.")


def _metric_to_dict(row) -> dict:
    return {
        "platform": row.platform,
        "account_id": row.account_id,
        "campaign_id": row.campaign_id,
        "campaign_name": row.campaign_name,
        "date": row.date.isoformat(),
        "impressions": row.impressions,
        "clicks": row.clicks,
        "spend": row.spend,
        "conversions": row.conversions,
        "conversion_value": row.conversion_value,
        "ctr": row.ctr,
        "cpc": row.cpc,
        "cost_per_conversion": row.cost_per_conversion,
        "roas": row.roas,
    }


def _aggregate_metric_rows(rows: list, by_day: bool = False) -> list[dict]:
    buckets: dict[tuple, dict] = {}
    for row in rows:
        key = (row.date, row.platform) if by_day else (row.platform,)
        bucket = buckets.setdefault(
            key,
            {
                "date": row.date.isoformat() if by_day else None,
                "platform": row.platform,
                "impressions": 0,
                "clicks": 0,
                "spend": 0.0,
                "conversions": 0.0,
                "conversion_value": 0.0,
            },
        )
        bucket["impressions"] += row.impressions
        bucket["clicks"] += row.clicks
        bucket["spend"] += row.spend
        bucket["conversions"] += row.conversions
        bucket["conversion_value"] += row.conversion_value

    output = []
    for bucket in buckets.values():
        impressions = bucket["impressions"]
        clicks = bucket["clicks"]
        spend = bucket["spend"]
        conversions = bucket["conversions"]
        value = bucket["conversion_value"]
        item = {
            "platform": bucket["platform"],
            "impressions": int(impressions),
            "clicks": int(clicks),
            "spend": round(float(spend), 2),
            "conversions": round(float(conversions), 2),
            "conversion_value": round(float(value), 2),
            **compute_derived_metrics(impressions, clicks, spend, conversions, value),
        }
        if by_day:
            item["date"] = bucket["date"]
        output.append(item)
    return sorted(output, key=lambda item: (item.get("date", ""), item["platform"]))
