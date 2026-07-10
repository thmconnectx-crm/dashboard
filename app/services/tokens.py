from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.config import get_settings
from app.models import OAuthToken
from app.services.crypto import decrypt_value, encrypt_value


def get_token(db: Session, platform: str) -> OAuthToken | None:
    token = db.query(OAuthToken).filter(OAuthToken.platform == platform).one_or_none()
    if token:
        set_committed_value(token, "access_token", decrypt_value(token.access_token))
        set_committed_value(token, "refresh_token", decrypt_value(token.refresh_token))
    return token


def get_effective_token(db: Session, platform: str) -> str:
    settings = get_settings()
    local = get_token(db, platform)
    if local and local.access_token:
        return local.access_token
    if platform == "google":
        return settings.google_ads_refresh_token
    if platform == "meta":
        return settings.meta_access_token
    return ""


def save_token(db: Session, platform: str, payload: dict) -> OAuthToken:
    token = get_token(db, platform) or OAuthToken(platform=platform)
    token.access_token = encrypt_value(payload.get("access_token", token.access_token or ""))
    token.refresh_token = encrypt_value(payload.get("refresh_token", token.refresh_token or ""))
    token.token_type = payload.get("token_type", token.token_type or "Bearer")
    expires_in = payload.get("expires_in")
    token.expires_at = (
        datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=int(expires_in))
        if expires_in
        else token.expires_at
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token
