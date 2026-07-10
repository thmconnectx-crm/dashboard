from functools import lru_cache
from pathlib import Path
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def _load_or_create_secret() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    secret_path = DATA_DIR / ".app_secret_key"
    if secret_path.exists():
        value = secret_path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(48)
    secret_path.write_text(value, encoding="utf-8")
    return value


class Settings(BaseSettings):
    app_name: str = "Paid Traffic Dashboard"
    app_secret_key: str = ""
    database_url: str = "sqlite:///./data/traffic_reports.sqlite3"
    base_url: str = "http://127.0.0.1:8000"
    environment: str = "local"
    trusted_hosts: str = "127.0.0.1,localhost"
    auto_sync_enabled: bool = False
    auto_sync_time: str = "03:00"
    auto_sync_period_days: int = 1
    auto_sync_platforms: str = "google,meta"

    google_ads_client_id: str = ""
    google_ads_client_secret: str = ""
    google_ads_developer_token: str = ""
    google_ads_login_customer_id: str = ""
    google_ads_api_version: str = "v24"
    google_ads_refresh_token: str = ""
    google_ads_customer_ids: str = ""

    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_graph_api_version: str = "v25.0"
    meta_access_token: str = ""
    meta_ad_account_ids: str = ""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:
        if not self.app_secret_key:
            self.app_secret_key = _load_or_create_secret()

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.base_url.rstrip('/')}/auth/google/callback"

    @property
    def meta_redirect_uri(self) -> str:
        return f"{self.base_url.rstrip('/')}/auth/meta/callback"

    def csv_list(self, value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        hosts = self.csv_list(self.trusted_hosts)
        return hosts or ["127.0.0.1", "localhost"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
