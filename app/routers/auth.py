import secrets

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.connectors.registry import get_connector, get_connectors
from app.config import get_settings
from app.db import create_session
from app.services.tokens import get_token


router = APIRouter(prefix="/auth", tags=["auth"])
_states: set[str] = set()


@router.get("/status")
def auth_status() -> dict:
    settings = get_settings()
    with create_session() as db:
        statuses = []
        for platform, connector in get_connectors().items():
            token = get_token(db, platform)
            env_token = settings.google_ads_refresh_token if platform == "google" else settings.meta_access_token
            statuses.append(
                {
                    "platform": platform,
                    "configured": connector.is_configured(),
                    "has_local_token": bool(token and token.access_token),
                    "has_refresh_token": bool(token and token.refresh_token),
                    "has_env_token": bool(env_token),
                }
            )
        return {"items": statuses}


@router.get("/{platform}/start")
def start_oauth(platform: str):
    try:
        connector = get_connector(platform)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not connector.is_configured():
        raise HTTPException(status_code=400, detail=f"Configure as credenciais de {platform} no .env primeiro.")
    state = secrets.token_urlsafe(24)
    _states.add(state)
    return RedirectResponse(connector.authorization_url(state))


@router.get("/{platform}/callback")
async def oauth_callback(platform: str, code: str = Query(""), state: str = Query("")):
    if state not in _states:
        raise HTTPException(status_code=400, detail="Estado OAuth invalido ou expirado.")
    _states.discard(state)
    try:
        connector = get_connector(platform)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await connector.exchange_code(code)
    return HTMLResponse(
        """
        <html>
          <body style="font-family: system-ui; padding: 32px;">
            <h1>Conexao concluida</h1>
            <p>O token foi salvo no banco SQLite local. Voce ja pode voltar ao dashboard.</p>
            <a href="/">Voltar para o dashboard</a>
          </body>
        </html>
        """
    )
