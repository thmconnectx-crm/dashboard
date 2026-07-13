from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ConnectorAccount:
    id: str
    name: str
    currency: str = ""


@dataclass(frozen=True)
class ConnectorCampaign:
    id: str
    account_id: str
    name: str
    status: str = ""
    objective: str = ""


@dataclass(frozen=True)
class ConnectorMetric:
    platform: str
    account_id: str
    campaign_id: str
    campaign_name: str
    date: date
    impressions: int = 0
    reach: int = 0
    clicks: int = 0
    spend: float = 0.0
    messages: float = 0.0
    conversions: float = 0.0
    conversion_value: float = 0.0
    ctr: float = 0.0
    cpc: float = 0.0
    cost_per_message: float = 0.0
    cost_per_conversion: float = 0.0
    roas: float = 0.0
    campaign_objective: str = ""


class AdsConnector(ABC):
    platform: str

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def authorization_url(self, state: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def exchange_code(self, code: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def get_accounts(self) -> list[ConnectorAccount]:
        raise NotImplementedError

    @abstractmethod
    async def get_campaigns(self, account_id: str) -> list[ConnectorCampaign]:
        raise NotImplementedError

    @abstractmethod
    async def get_metrics(
        self,
        account_id: str,
        start_date: date,
        end_date: date,
        campaign_ids: list[str] | None = None,
    ) -> list[ConnectorMetric]:
        raise NotImplementedError
