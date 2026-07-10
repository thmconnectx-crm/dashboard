from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.connectors.base import ConnectorAccount, ConnectorCampaign, ConnectorMetric
from app.models import Base
from app.services.history import (
    aggregate_by_platform,
    list_saved_accounts,
    list_saved_campaigns,
    query_metrics,
    upsert_accounts,
    upsert_campaigns,
    upsert_metrics,
)


def make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_history_upserts_and_aggregates():
    db = make_session()
    upsert_accounts(db, "google", [ConnectorAccount(id="123", name="Conta Demo", currency="BRL")])
    upsert_campaigns(db, "google", [ConnectorCampaign(id="c1", account_id="123", name="Campanha Demo", status="ENABLED")])
    upsert_metrics(
        db,
        [
            ConnectorMetric(
                platform="google",
                account_id="123",
                campaign_id="c1",
                campaign_name="Campanha Demo",
                date=date(2026, 7, 10),
                impressions=1000,
                clicks=100,
                spend=250.0,
                conversions=10,
                conversion_value=1000.0,
                ctr=10.0,
                cpc=2.5,
                cost_per_conversion=25.0,
                roas=4.0,
            )
        ],
    )

    assert len(list_saved_accounts(db)) == 1
    assert len(list_saved_campaigns(db)) == 1
    rows = query_metrics(db, date(2026, 7, 1), date(2026, 7, 31))
    assert len(rows) == 1

    summary = aggregate_by_platform(db, date(2026, 7, 1), date(2026, 7, 31))
    assert summary[0]["platform"] == "google"
    assert summary[0]["ctr"] == 10.0
    assert summary[0]["roas"] == 4.0
