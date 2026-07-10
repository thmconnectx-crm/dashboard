from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import Base, CampaignMetric


def make_test_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    db.add(
        CampaignMetric(
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
    )
    db.commit()
    return TestingSession


def test_dashboard_and_metrics_endpoints_use_saved_data():
    TestingSession = make_test_db()

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app, base_url="http://127.0.0.1")

    dashboard = client.get("/api/dashboard?period=custom&start_date=2026-07-01&end_date=2026-07-31")
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["summary"][0]["spend"] == 250.0
    assert payload["summary"][0]["roas"] == 4.0

    metrics = client.get("/api/metrics?start_date=2026-07-01&end_date=2026-07-31")
    assert metrics.status_code == 200
    assert metrics.json()["items"][0]["campaign_name"] == "Campanha Demo"

    app.dependency_overrides.clear()


def test_pdf_export_endpoint_returns_pdf():
    TestingSession = make_test_db()

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app, base_url="http://127.0.0.1")

    response = client.get("/api/export/pdf?start_date=2026-07-01&end_date=2026-07-31")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")

    app.dependency_overrides.clear()
