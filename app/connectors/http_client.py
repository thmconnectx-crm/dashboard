import asyncio
from typing import Any

import httpx

from app.services.logging_config import get_logger


class AdsApiError(RuntimeError):
    pass


RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    platform: str,
    *,
    attempts: int = 3,
    **kwargs: Any,
) -> Any:
    logger = get_logger()
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = await client.request(method, url, **kwargs)
            if response.status_code in RETRY_STATUS_CODES and attempt < attempts:
                await asyncio.sleep(0.7 * attempt)
                continue
            if response.is_error:
                message = _format_error(platform, response)
                logger.error("api_error platform=%s status=%s message=%s", platform, response.status_code, message)
                raise AdsApiError(message)
            return response.json()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = exc
            if attempt < attempts:
                await asyncio.sleep(0.7 * attempt)
                continue
            message = f"{_platform_label(platform)}: falha temporaria de rede apos {attempts} tentativas ({exc})."
            logger.error("api_network_error platform=%s message=%s", platform, message)
            raise AdsApiError(message) from exc
    raise AdsApiError(str(last_error) if last_error else f"{_platform_label(platform)}: falha inesperada de API.")


def _format_error(platform: str, response: httpx.Response) -> str:
    payload = _safe_json(response)
    detail = _extract_detail(payload) or response.text[:500]
    prefix = _platform_label(platform)
    hint = _status_hint(platform, response.status_code, detail)
    return f"{prefix}: {hint} Detalhe: {detail}".strip()


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {}


def _extract_detail(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    if "error_description" in payload:
        return str(payload["error_description"])
    if "error" in payload:
        error = payload["error"]
        if isinstance(error, dict):
            parts = [
                str(error.get("message", "")),
                str(error.get("status", "")),
                str(error.get("code", "")),
            ]
            details = error.get("details")
            if details:
                parts.append(str(details))
            return " | ".join(part for part in parts if part)
        return str(error)
    return str(payload)


def _status_hint(platform: str, status_code: int, detail: str) -> str:
    lower = detail.lower()
    if status_code in {401, 403}:
        if "developer" in lower and platform == "google":
            return "developer token ausente, invalido ou ainda nao aprovado."
        if "permission" in lower or "permissions" in lower or "scope" in lower:
            return "permissao/escopo insuficiente para acessar essa conta."
        return "token expirado, revogado ou sem acesso a conta solicitada."
    if status_code == 429:
        return "limite de requisicoes atingido. Tente novamente em alguns minutos."
    if status_code >= 500:
        return "servico da API indisponivel ou instavel no momento."
    if status_code == 400:
        return "requisicao recusada pela API. Verifique IDs de conta, filtros e credenciais."
    return f"erro HTTP {status_code}."


def _platform_label(platform: str) -> str:
    return "Google Ads" if platform == "google" else "Meta Ads"
