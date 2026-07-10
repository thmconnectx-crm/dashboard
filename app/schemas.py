from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


Platform = Literal["google", "meta"]


class DateRange(BaseModel):
    start_date: date
    end_date: date


class SyncRequest(BaseModel):
    platforms: list[Platform] = Field(default_factory=lambda: ["google", "meta"])
    start_date: date
    end_date: date
    account_ids: list[str] = Field(default_factory=list)
    campaign_ids: list[str] = Field(default_factory=list)


class MetricRow(BaseModel):
    platform: str
    account_id: str
    campaign_id: str
    campaign_name: str
    date: date
    impressions: int
    clicks: int
    spend: float
    conversions: float
    conversion_value: float
    ctr: float
    cpc: float
    cost_per_conversion: float
    roas: float


class TokenStatus(BaseModel):
    platform: str
    configured: bool
    has_local_token: bool
