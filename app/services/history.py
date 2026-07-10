from datetime import date

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorAccount, ConnectorCampaign, ConnectorMetric
from app.models import AdAccount, Campaign, CampaignMetric
from app.services.metrics import compute_derived_metrics


def upsert_accounts(db: Session, platform: str, accounts: list[ConnectorAccount]) -> None:
    for account in accounts:
        row = (
            db.query(AdAccount)
            .filter(AdAccount.platform == platform, AdAccount.external_id == account.id)
            .one_or_none()
        )
        row = row or AdAccount(platform=platform, external_id=account.id)
        row.name = account.name
        row.currency = account.currency
        db.add(row)
    db.commit()


def upsert_campaigns(db: Session, platform: str, campaigns: list[ConnectorCampaign]) -> None:
    for campaign in campaigns:
        row = (
            db.query(Campaign)
            .filter(
                Campaign.platform == platform,
                Campaign.account_id == campaign.account_id,
                Campaign.external_id == campaign.id,
            )
            .one_or_none()
        )
        row = row or Campaign(platform=platform, account_id=campaign.account_id, external_id=campaign.id)
        row.name = campaign.name
        row.status = campaign.status
        db.add(row)
    db.commit()


def upsert_metrics(db: Session, metrics: list[ConnectorMetric]) -> None:
    for metric in metrics:
        row = (
            db.query(CampaignMetric)
            .filter(
                CampaignMetric.platform == metric.platform,
                CampaignMetric.account_id == metric.account_id,
                CampaignMetric.campaign_id == metric.campaign_id,
                CampaignMetric.date == metric.date,
            )
            .one_or_none()
        )
        row = row or CampaignMetric(
            platform=metric.platform,
            account_id=metric.account_id,
            campaign_id=metric.campaign_id,
            date=metric.date,
        )
        row.campaign_name = metric.campaign_name
        row.impressions = metric.impressions
        row.clicks = metric.clicks
        row.spend = metric.spend
        row.conversions = metric.conversions
        row.conversion_value = metric.conversion_value
        row.ctr = metric.ctr
        row.cpc = metric.cpc
        row.cost_per_conversion = metric.cost_per_conversion
        row.roas = metric.roas
        db.add(row)
    db.commit()


def list_saved_accounts(db: Session, platform: str | None = None) -> list[AdAccount]:
    query = db.query(AdAccount)
    if platform:
        query = query.filter(AdAccount.platform == platform)
    return query.order_by(AdAccount.platform, AdAccount.name).all()


def list_saved_campaigns(db: Session, platform: str | None = None, account_id: str | None = None) -> list[Campaign]:
    query = db.query(Campaign)
    if platform:
        query = query.filter(Campaign.platform == platform)
    if account_id:
        query = query.filter(Campaign.account_id == account_id)
    return query.order_by(Campaign.platform, Campaign.name).all()


def query_metrics(
    db: Session,
    start_date: date,
    end_date: date,
    platforms: list[str] | None = None,
    account_ids: list[str] | None = None,
    campaign_ids: list[str] | None = None,
) -> list[CampaignMetric]:
    filters = [CampaignMetric.date >= start_date, CampaignMetric.date <= end_date]
    if platforms:
        filters.append(CampaignMetric.platform.in_(platforms))
    if account_ids:
        filters.append(CampaignMetric.account_id.in_(account_ids))
    if campaign_ids:
        filters.append(CampaignMetric.campaign_id.in_(campaign_ids))
    return db.query(CampaignMetric).filter(and_(*filters)).order_by(CampaignMetric.date).all()


def aggregate_by_platform(db: Session, start_date: date, end_date: date) -> list[dict]:
    rows = (
        db.query(
            CampaignMetric.platform,
            func.sum(CampaignMetric.impressions),
            func.sum(CampaignMetric.clicks),
            func.sum(CampaignMetric.spend),
            func.sum(CampaignMetric.conversions),
            func.sum(CampaignMetric.conversion_value),
        )
        .filter(CampaignMetric.date >= start_date, CampaignMetric.date <= end_date)
        .group_by(CampaignMetric.platform)
        .all()
    )
    return [
        _computed_totals(platform, impressions or 0, clicks or 0, spend or 0, conversions or 0, value or 0)
        for platform, impressions, clicks, spend, conversions, value in rows
    ]


def aggregate_by_day(db: Session, start_date: date, end_date: date) -> list[dict]:
    rows = (
        db.query(
            CampaignMetric.date,
            CampaignMetric.platform,
            func.sum(CampaignMetric.impressions),
            func.sum(CampaignMetric.clicks),
            func.sum(CampaignMetric.spend),
            func.sum(CampaignMetric.conversions),
            func.sum(CampaignMetric.conversion_value),
        )
        .filter(CampaignMetric.date >= start_date, CampaignMetric.date <= end_date)
        .group_by(CampaignMetric.date, CampaignMetric.platform)
        .order_by(CampaignMetric.date)
        .all()
    )
    return [
        {
            "date": row_date.isoformat(),
            **_computed_totals(platform, impressions or 0, clicks or 0, spend or 0, conversions or 0, value or 0),
        }
        for row_date, platform, impressions, clicks, spend, conversions, value in rows
    ]


def _computed_totals(platform: str, impressions: int, clicks: int, spend: float, conversions: float, value: float) -> dict:
    derived = compute_derived_metrics(impressions, clicks, spend, conversions, value)
    return {
        "platform": platform,
        "impressions": int(impressions),
        "clicks": int(clicks),
        "spend": round(float(spend), 2),
        "conversions": round(float(conversions), 2),
        "conversion_value": round(float(value), 2),
        **derived,
    }
