from datetime import date
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.connectors.base import AdsConnector, ConnectorAccount, ConnectorCampaign, ConnectorMetric
from app.connectors.http_client import request_json
from app.db import create_session
from app.services.tokens import get_token, save_token


class MetaAdsConnector(AdsConnector):
    platform = "meta"
    scopes = ["ads_read", "business_management"]

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return bool(self.settings.meta_app_id and self.settings.meta_app_secret)

    def authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.settings.meta_app_id,
            "redirect_uri": self.settings.meta_redirect_uri,
            "state": state,
            "scope": ",".join(self.scopes),
            "response_type": "code",
        }
        return f"https://www.facebook.com/{self.settings.meta_graph_api_version}/dialog/oauth?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        params = {
            "client_id": self.settings.meta_app_id,
            "client_secret": self.settings.meta_app_secret,
            "redirect_uri": self.settings.meta_redirect_uri,
            "code": code,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            token_payload = await request_json(client, "GET", self._graph_url("oauth/access_token"), self.platform, params=params)
        with create_session() as db:
            save_token(db, self.platform, token_payload)
        return token_payload

    async def get_accounts(self) -> list[ConnectorAccount]:
        configured_ids = self.settings.csv_list(self.settings.meta_ad_account_ids)
        if configured_ids:
            return [
                ConnectorAccount(id=_normalize_account_id(account_id), name=f"Meta Ads {_normalize_account_id(account_id)}")
                for account_id in configured_ids
            ]

        token = self._access_token()
        params = {
            "access_token": token,
            "fields": "id,name,currency,account_status",
            "limit": 100,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            payload = await request_json(client, "GET", self._graph_url("me/adaccounts"), self.platform, params=params)
        return [
            ConnectorAccount(id=item["id"], name=item.get("name", item["id"]), currency=item.get("currency", ""))
            for item in payload.get("data", [])
        ]

    async def get_campaigns(self, account_id: str) -> list[ConnectorCampaign]:
        token = self._access_token()
        params = {
            "access_token": token,
            "fields": "id,name,status,effective_status,objective",
            "limit": 200,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            payload = await request_json(client, "GET", self._graph_url(f"{_normalize_account_id(account_id)}/campaigns"), self.platform, params=params)
        return [
            ConnectorCampaign(
                id=item["id"],
                account_id=_normalize_account_id(account_id),
                name=item.get("name", "Sem nome"),
                status=item.get("effective_status") or item.get("status", ""),
                objective=item.get("objective", ""),
            )
            for item in payload.get("data", [])
        ]

    async def get_metrics(
        self,
        account_id: str,
        start_date: date,
        end_date: date,
        campaign_ids: list[str] | None = None,
    ) -> list[ConnectorMetric]:
        token = self._access_token()
        filtering = []
        if campaign_ids:
            filtering.append({"field": "campaign.id", "operator": "IN", "value": campaign_ids})
        params = {
            "access_token": token,
            "level": "campaign",
            "time_increment": 1,
            "time_range": f'{{"since":"{start_date.isoformat()}","until":"{end_date.isoformat()}"}}',
            "fields": ",".join(
                [
                    "date_start",
                    "campaign_id",
                    "campaign_name",
                    "reach",
                    "impressions",
                    "clicks",
                    "ctr",
                    "cpc",
                    "spend",
                    "actions",
                    "action_values",
                    "purchase_roas",
                ]
            ),
            "limit": 500,
        }
        if filtering:
            params["filtering"] = str(filtering).replace("'", '"')

        async with httpx.AsyncClient(timeout=60) as client:
            payload = await request_json(client, "GET", self._graph_url(f"{_normalize_account_id(account_id)}/insights"), self.platform, params=params)

        campaign_objectives = _campaign_objectives_from_db(self.platform, _normalize_account_id(account_id))
        metrics: list[ConnectorMetric] = []
        for item in payload.get("data", []):
            campaign_id = item.get("campaign_id", "")
            spend = float(item.get("spend", 0) or 0)
            clicks = int(item.get("clicks", 0) or 0)
            reach = int(item.get("reach", 0) or 0)
            messages = _sum_messages(item.get("actions", []))
            conversions = messages or _sum_conversions(item.get("actions", []))
            conversion_value = _sum_actions(item.get("action_values", []))
            roas = _extract_roas(item.get("purchase_roas", []), spend, conversion_value)
            cost_per_message = round(spend / messages, 2) if messages else 0.0
            metrics.append(
                ConnectorMetric(
                    platform=self.platform,
                    account_id=_normalize_account_id(account_id),
                    campaign_id=campaign_id,
                    campaign_name=item.get("campaign_name", "Sem nome"),
                    campaign_objective=campaign_objectives.get(campaign_id, ""),
                    date=date.fromisoformat(item["date_start"]),
                    impressions=int(item.get("impressions", 0) or 0),
                    reach=reach,
                    clicks=clicks,
                    spend=round(spend, 2),
                    messages=messages,
                    conversions=conversions,
                    conversion_value=conversion_value,
                    ctr=float(item.get("ctr", 0) or 0),
                    cpc=float(item.get("cpc", 0) or 0) if clicks else 0.0,
                    cost_per_message=cost_per_message,
                    cost_per_conversion=round(spend / conversions, 2) if conversions else 0.0,
                    roas=roas,
                )
            )
        return metrics

    def _access_token(self) -> str:
        with create_session() as db:
            local_token = get_token(db, self.platform)
            if local_token and local_token.access_token:
                return local_token.access_token
        if self.settings.meta_access_token:
            return self.settings.meta_access_token
        raise RuntimeError("Meta Ads nao possui token local nem META_ACCESS_TOKEN no .env.")

    def _graph_url(self, path: str) -> str:
        return f"https://graph.facebook.com/{self.settings.meta_graph_api_version}/{path.lstrip('/')}"


def _normalize_account_id(account_id: str) -> str:
    clean = account_id.strip()
    return clean if clean.startswith("act_") else f"act_{clean}"


def _campaign_objectives_from_db(platform: str, account_id: str) -> dict[str, str]:
    from app.models import Campaign

    with create_session() as db:
        rows = db.query(Campaign).filter(Campaign.platform == platform, Campaign.account_id == account_id).all()
        return {row.external_id: row.objective for row in rows}


def _sum_actions(actions: list[dict]) -> float:
    if not actions:
        return 0.0
    return round(sum(float(action.get("value", 0) or 0) for action in actions), 2)


def _sum_messages(actions: list[dict]) -> float:
    if not actions:
        return 0.0
    conversation_started_types = {
        "onsite_conversion.messaging_conversation_started_7d",
        "messaging_conversation_started_7d",
    }
    total = 0.0
    for action in actions:
        action_type = action.get("action_type", "")
        if action_type in conversation_started_types:
            total += float(action.get("value", 0) or 0)
    return round(total, 2)


def _sum_conversions(actions: list[dict]) -> float:
    if not actions:
        return 0.0
    preferred = {
        "purchase",
        "offsite_conversion.fb_pixel_purchase",
        "onsite_conversion.purchase",
        "lead",
        "offsite_conversion.fb_pixel_lead",
    }
    total = 0.0
    for action in actions:
        if action.get("action_type") in preferred:
            total += float(action.get("value", 0) or 0)
    if total:
        return round(total, 2)
    return round(sum(float(action.get("value", 0) or 0) for action in actions), 2)


def _extract_roas(roas_rows: list[dict], spend: float, conversion_value: float) -> float:
    for row in roas_rows or []:
        if "value" in row:
            return round(float(row["value"] or 0), 2)
    return round(conversion_value / spend, 2) if spend else 0.0
