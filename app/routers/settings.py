import os
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.models.facebook_connection import FacebookConnection
from app.services.facebook_api import FacebookApiError, FacebookApiService
from app.services.meta_config_service import MetaConfigService
from app.services.settings_service import SettingsService
from app.services.social_account_service import SocialAccountService


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
settings_service = SettingsService()
meta_config_service = MetaConfigService()


@router.get("/settings")
def einstellungen(
    request: Request,
    connected: bool = False,
    disconnected: bool = False,
    pages_saved: bool = False,
    facebook_error: str | None = None,
    account_saved: int = 0,
    account_deleted: int = 0,
    account_error: str | None = None,
):
    meta_config = meta_config_service.load()
    connection = meta_config_service.load_connection()
    facebook_pages = settings_service.load_pages()
    social_accounts = SocialAccountService().list_accounts()

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "facebook_pages": facebook_pages,
            "active_page_count": sum(1 for page in facebook_pages if page.is_active),
            "meta_app_id": meta_config.app_id,
            "meta_redirect_uri": meta_config.redirect_uri,
            "meta_is_configured": meta_config.is_configured,
            "meta_uses_business_login": meta_config.uses_business_login,
            "facebook_is_connected": bool(meta_config.user_access_token),
            "facebook_connection": connection,
            "connected": connected,
            "disconnected": disconnected,
            "pages_saved": pages_saved,
            "facebook_error": facebook_error,
            "social_accounts": social_accounts,
            "account_saved": bool(account_saved),
            "account_deleted": bool(account_deleted),
            "account_error": account_error,
        },
    )


@router.get("/facebook/connect")
def facebook_verbinden(request: Request):
    meta_config = meta_config_service.load()
    if not meta_config.is_configured:
        return _settings_error(
            "Die Meta-App ist nicht vollständig konfiguriert. App-ID, App-Secret und Redirect-URI müssen gesetzt sein."
        )

    state = secrets.token_urlsafe(32)
    request.session["facebook_oauth_state"] = state

    try:
        login_url = FacebookApiService(meta_config).build_login_url(state=state)
    except FacebookApiError as error:
        return _settings_error(str(error))

    return RedirectResponse(url=login_url, status_code=302)


@router.get("/facebook/callback")
def facebook_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    if error:
        return _settings_error(error_description or error or "Die Facebook-Anmeldung wurde abgebrochen.")

    saved_state = str(request.session.pop("facebook_oauth_state", ""))
    if not state or not saved_state or not secrets.compare_digest(state, saved_state):
        return _settings_error(
            "Die Sicherheitsprüfung des Facebook-Logins ist fehlgeschlagen. Bitte starte die Verbindung erneut."
        )
    if not code:
        return _settings_error("Facebook hat keinen Anmeldecode zurückgegeben.")

    meta_config = meta_config_service.load()
    facebook_api = FacebookApiService(meta_config)

    try:
        short_token = facebook_api.exchange_code_for_token(code=code)
        try:
            final_token = facebook_api.exchange_for_long_lived_token(short_token.access_token)
        except FacebookApiError:
            final_token = short_token

        user = facebook_api.get_user(final_token.access_token)
        new_pages = facebook_api.get_managed_pages(final_token.access_token)
        if not new_pages:
            raise FacebookApiError(
                "Facebook hat keine freigegebenen Seiten zurückgegeben. Prüfe die Berechtigungen pages_show_list, pages_read_engagement und pages_manage_posts sowie die Seitenauswahl im Facebook-Login."
            )

        old_pages = {page.page_id: page for page in settings_service.load_pages()}
        for page in new_pages:
            old_page = old_pages.get(page.page_id)
            if old_page:
                page.is_active = old_page.is_active
                page.is_default = old_page.is_default

        previous = meta_config_service.load_connection()
        connection = FacebookConnection.create(
            user_id=user.user_id,
            user_name=user.name,
            token_type=final_token.token_type,
            expires_in=final_token.expires_in,
            previous_connected_at=previous.connected_at,
        )

        meta_config_service.save_user_access_token(final_token.access_token)
        meta_config_service.save_connection(connection)
        settings_service.save_pages(new_pages)
    except FacebookApiError as api_error:
        return _settings_error(str(api_error))

    return RedirectResponse(url="/settings?connected=true", status_code=303)


@router.post("/facebook/pages")
def facebook_seiten_speichern(active_page_ids: list[str] = Form(default=[])):
    active_ids = {str(page_id).strip() for page_id in active_page_ids if str(page_id).strip()}
    pages = settings_service.load_pages()
    for page in pages:
        page.is_active = page.page_id in active_ids
    settings_service.save_pages(pages)
    return RedirectResponse(url="/settings?pages_saved=true", status_code=303)


@router.post("/facebook/disconnect")
def facebook_trennen():
    meta_config_service.delete_user_access_token()
    meta_config_service.delete_connection()
    settings_service.save_pages([])
    return RedirectResponse(url="/settings?disconnected=true", status_code=303)


@router.post("/settings/accounts")
def konto_hinzufuegen(
    platform: str = Form(...),
    name: str = Form(...),
    external_id: str = Form(""),
):
    platform = platform.strip().lower()
    name = name.strip()
    if platform not in {"facebook", "instagram", "x", "tiktok"} or not name:
        return RedirectResponse(url="/settings?account_error=Ungültige Kontodaten", status_code=303)
    SocialAccountService().create(platform=platform, name=name, external_id=external_id)
    return RedirectResponse(url="/settings?account_saved=1", status_code=303)


@router.post("/settings/accounts/{account_id}/toggle")
def konto_umschalten(account_id: str):
    SocialAccountService().toggle(account_id)
    return RedirectResponse(url="/settings?account_saved=1", status_code=303)


@router.post("/settings/accounts/{account_id}/delete")
def konto_loeschen(account_id: str):
    SocialAccountService().delete(account_id)
    return RedirectResponse(url="/settings?account_deleted=1", status_code=303)


def _settings_error(message: str) -> RedirectResponse:
    return RedirectResponse(
        url="/settings?facebook_error=" + quote(message),
        status_code=303,
    )
