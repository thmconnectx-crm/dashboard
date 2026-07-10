from datetime import date, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.connectors.base import AdsConnector, ConnectorAccount, ConnectorCampaign, ConnectorMetric
from app.connectors.http_client import request_json
from app.db import create_session
from app.services.tokens import get_token, save_token


class GoogleAdsConnector(AdsConnector):
    platform = "google"
    scope = "https://www.googleapis.com/auth/adwords"

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return all(
            [
                self.settings.google_ads_client_id,
                self.settings.google_ads_client_secret,
                self.settings.google_ads_developer_token,
            ]
        )

    def authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.settings.google_ads_client_id,
            "redirect_uri": self.settings.google_redirect_uri,
            "response_type": "code",
            "scope": self.scope,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        payload = {
            "code": code,
            "client_id": self.settings.google_ads_client_id,
            "client_secret": self.settings.google_ads_client_secret,
            "redirect_uri": self.settings.google_redirect_uri,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            token_payload = await request_json(client, "POST", "https://oauth2.googleapis.com/token", self.platform, data=payload)
        with create_session() as db:
            save_token(db, self.platform, token_payload)
        return token_payload

    async def get_accounts(self) -> list[ConnectorAccount]:
        configured_ids = self.settings.csv_list(self.settings.google_ads_customer_ids)
        if configured_ids:
            return [ConnectorAccount(id=customer_id, name=f"Google Ads {customer_id}") for customer_id in configured_ids]

        access_token = await self._access_token()
        url = f"https://googleads.googleapis.com/{self.settings.google_ads_api_version}/customers:listAccessibleCustomers"
        async with httpx.AsyncClient(timeout=30) as client:
            payload = await request_json(client, "GET", url, self.platform, headers=self._headers(access_token))
        accounts = []
        for resource_name in payload.get("resourceNames", []):
            customer_id = resource_name.split("/")[-1]
            accounts.append(ConnectorAccount(id=customer_id, name=f"Google Ads {customer_id}"))
        return accounts

    async def get_campaigns(self, account_id: str) -> list[ConnectorCampaign]:
        query = """
            SELECT
              campaign.id,
              campaign.name,
              campaign.status
            FROM campaign
            ORDER BY campaign.name
        """
        rows = await self._search_stream(account_id, query)
        campaigns: list[ConnectorCampaign] = []
        for row in rows:
            campaign = row.get("campaign", {})
            campaigns.append(
                ConnectorCampaign(
                    id=str(campaign.get("id", "")),
                    account_id=account_id,
                    name=campaign.get("name", "Sem nome"),
                    status=campaign.get("status", ""),
                )
            )
        return campaigns

    async def get_metrics(
        self,
        account_id: str,
        start_date: date,
        end_date: date,
        campaign_ids: list[str] | None = None,
    ) -> list[ConnectorMetric]:
        campaign_filter = ""
        if campaign_ids:
            ids = ",".join(campaign_ids)
            campaign_filter = f" AND campaign.id IN ({ids})"
        query = f"""
            SELECT
              segments.date,
              campaign.id,
              campaign.name,
              metrics.impressions,
              metrics.clicks,
              metrics.ctr,
              metrics.average_cpc,
              metrics.cost_micros,
              metrics.conversions,
              metrics.conversions_value,
              metrics.cost_per_conversion,
              metrics.conversions_value_per_cost
            FROM campaign
            WHERE segments.date BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'
            {campaign_filter}
            ORDER BY segments.date
        """
        rows = await self._search_stream(account_id, query)
        metrics: list[ConnectorMetric] = []
        for row in rows:
            campaign = row.get("campaign", {})
            api_metrics = row.get("metrics", {})
            spend = _micros_to_unit(api_metrics.get("costMicros", 0))
            clicks = int(api_metrics.get("clicks", 0) or 0)
            conversions = float(api_metrics.get("conversions", 0) or 0)
            conversion_value = float(api_metrics.get("conversionsValue", 0) or 0)
            metrics.append(
                ConnectorMetric(
                    platform=self.platform,
                    account_id=account_id,
                    campaign_id=str(campaign.get("id", "")),
                    campaign_name=campaign.get("name", "Sem nome"),
                    date=date.fromisoformat(row.get("segments", {}).get("date")),
                    impressions=int(api_metrics.get("impressions", 0) or 0),
                    clicks=clicks,
                    spend=spend,
                    conversions=conversions,
                    conversion_value=conversion_value,
                    ctr=float(api_metrics.get("ctr", 0) or 0) * 100,
                    cpc=_micros_to_unit(api_metrics.get("averageCpc", 0)) if clicks else 0.0,
                    cost_per_conversion=_micros_to_unit(api_metrics.get("costPerConversion", 0))
                    if conversions
                    else 0.0,
                    roas=float(api_metrics.get("conversionsValuePerCost", 0) or 0),
                )
            )
        return metrics

    async def _search_stream(self, customer_id: str, query: str) -> list[dict]:
        access_token = await self._access_token()
        clean_customer_id = customer_id.replace("-", "")
        url = (
            f"https://googleads.googleapis.com/{self.settings.google_ads_api_version}/"
            f"customers/{clean_customer_id}/googleAds:searchStream"
        )
        async with httpx.AsyncClient(timeout=60) as client:
            payload = await request_json(client, "POST", url, self.platform, json={"query": query}, headers=self._headers(access_token))
        rows: list[dict] = []
        for batch in payload:
            rows.extend(batch.get("results", []))
        return rows

    async def _access_token(self) -> str:
        with create_session() as db:
            local_token = get_token(db, self.platform)
            if (
                local_token
                and local_token.access_token
                and local_token.expires_at
                and local_token.expires_at > datetime.utcnow() + timedelta(seconds=60)
            ):
                return local_token.access_token
            refresh_token = local_token.refresh_token if local_token and local_token.refresh_token else ""

        refresh_token = refresh_token or self.settings.google_ads_refresh_token
        if not refresh_token:
            raise RuntimeError("Google Ads nao possui token local nem GOOGLE_ADS_REFRESH_TOKEN no .env.")

        payload = {
            "client_id": self.settings.google_ads_client_id,
            "client_secret": self.settings.google_ads_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            token_payload = await request_json(client, "POST", "https://oauth2.googleapis.com/token", self.platform, data=payload)
        token_payload["refresh_token"] = refresh_token
        with create_session() as db:
            save_token(db, self.platform, token_payload)
        return token_payload["access_token"]

    def _headers(self, access_token: str) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": self.settings.google_ads_developer_token,
            "Content-Type": "application/json",
        }
        if self.settings.google_ads_login_customer_id:
            headers["login-customer-id"] = self.settings.google_ads_login_customer_id.replace("-", "")
        return headers


def _micros_to_unit(value: int | float | str | None) -> float:
    return round(float(value or 0) / 1_000_000, 2)
