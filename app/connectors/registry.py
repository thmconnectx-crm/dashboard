from app.connectors.base import AdsConnector
from app.connectors.google_ads import GoogleAdsConnector
from app.connectors.meta_ads import MetaAdsConnector


def get_connectors() -> dict[str, AdsConnector]:
    return {
        "google": GoogleAdsConnector(),
        "meta": MetaAdsConnector(),
    }


def get_connector(platform: str) -> AdsConnector:
    connectors = get_connectors()
    if platform not in connectors:
        raise KeyError(f"Conector desconhecido: {platform}")
    return connectors[platform]
