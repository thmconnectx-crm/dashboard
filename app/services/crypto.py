import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


TOKEN_PREFIX = "fernet:"


def _fernet() -> Fernet:
    secret = get_settings().app_secret_key.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_value(value: str | None) -> str:
    if not value:
        return ""
    if value.startswith(TOKEN_PREFIX):
        return value
    encrypted = _fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{TOKEN_PREFIX}{encrypted}"


def decrypt_value(value: str | None) -> str:
    if not value:
        return ""
    if not value.startswith(TOKEN_PREFIX):
        return value
    token = value.removeprefix(TOKEN_PREFIX)
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Nao foi possivel descriptografar token. Verifique se APP_SECRET_KEY e o mesmo usado ao salvar o token.") from exc
