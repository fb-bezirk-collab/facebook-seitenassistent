import os
import secrets
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Request,
    Form,
)
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.services.facebook_api import (
    FacebookApiError,
    FacebookApiService,
)
from app.services.meta_config_service import (
    MetaConfigService,
)
from app.services.settings_service import (
    SettingsService,
)


router = APIRouter()

templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR)
)

settings_service = SettingsService()
meta_config_service = MetaConfigService()


@router.get("/settings")
def einstellungen(
    request: Request,
    connected: bool = False,
    facebook_error: str | None = None,
    account_saved: int = 0,
    account_deleted: int = 0,
    account_error: str | None = None,
):
    meta_config = meta_config_service.load()
    facebook_pages = settings_service.load_pages()
    from app.services.social_account_service import SocialAccountService
    social_accounts = SocialAccountService().list_accounts()

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "facebook_pages": facebook_pages,
            "meta_app_id": meta_config.app_id,
            "meta_is_configured": (
                meta_config.is_configured
            ),
            "facebook_is_connected": bool(
                meta_config.user_access_token
                and facebook_pages
            ),
            "connected": connected,
            "facebook_error": facebook_error,
            "social_accounts": social_accounts,
            "account_saved": bool(account_saved),
            "account_deleted": bool(account_deleted),
            "account_error": account_error,
        },
    )


@router.get("/facebook/connect")
def facebook_verbinden():
    meta_config = meta_config_service.load()

    if not meta_config.is_configured:
        return RedirectResponse(
            url=(
                "/settings?facebook_error="
                + quote(
                    "Die Meta-App ist nicht "
                    "vollständig konfiguriert."
                )
            ),
            status_code=303,
        )

    state = secrets.token_urlsafe(32)

    facebook_api = FacebookApiService(
        config=meta_config
    )

    try:
        login_url = facebook_api.build_login_url(
            state=state
        )

    except FacebookApiError as error:
        return RedirectResponse(
            url=(
                "/settings?facebook_error="
                + quote(str(error))
            ),
            status_code=303,
        )

    response = RedirectResponse(
        url=login_url,
        status_code=302,
    )

    response.set_cookie(
        key="facebook_oauth_state",
        value=state,
        max_age=600,
        httponly=True,
        secure=bool(os.getenv("RAILWAY_ENVIRONMENT")),
        samesite="lax",
    )

    return response


@router.get("/facebook/callback")
def facebook_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    if error:
        message = (
            error_description
            or error
            or "Die Facebook-Anmeldung "
            "wurde abgebrochen."
        )

        return RedirectResponse(
            url=(
                "/settings?facebook_error="
                + quote(message)
            ),
            status_code=303,
        )

    saved_state = request.cookies.get(
        "facebook_oauth_state"
    )

    if (
        not state
        or not saved_state
        or not secrets.compare_digest(
            state,
            saved_state,
        )
    ):
        return RedirectResponse(
            url=(
                "/settings?facebook_error="
                + quote(
                    "Die Sicherheitsprüfung des "
                    "Facebook-Logins ist fehlgeschlagen. "
                    "Bitte starte die Verbindung erneut."
                )
            ),
            status_code=303,
        )

    if not code:
        return RedirectResponse(
            url=(
                "/settings?facebook_error="
                + quote(
                    "Facebook hat keinen "
                    "Anmeldecode zurückgegeben."
                )
            ),
            status_code=303,
        )

    meta_config = meta_config_service.load()

    facebook_api = FacebookApiService(
        config=meta_config
    )

    try:
        short_token = (
            facebook_api.exchange_code_for_token(
                code=code
            )
        )

        try:
            final_token = (
                facebook_api
                .exchange_for_long_lived_token(
                    short_token.access_token
                )
            )
        except FacebookApiError:
            final_token = short_token

        pages = facebook_api.get_managed_pages(
            user_access_token=(
                final_token.access_token
            )
        )

        if not pages:
            raise FacebookApiError(
                "Facebook hat keine freigegebenen "
                "Seiten zurückgegeben. Prüfe, ob du "
                "in der Login-Konfiguration die Seiten "
                "und die erforderlichen Berechtigungen "
                "ausgewählt hast."
            )

        meta_config_service.save_user_access_token(
            final_token.access_token
        )

        settings_service.save_pages(pages)

    except FacebookApiError as error:
        response = RedirectResponse(
            url=(
                "/settings?facebook_error="
                + quote(str(error))
            ),
            status_code=303,
        )

        response.delete_cookie(
            "facebook_oauth_state"
        )

        return response

    response = RedirectResponse(
        url="/settings?connected=true",
        status_code=303,
    )

    response.delete_cookie(
        "facebook_oauth_state"
    )

    return response

@router.post("/settings/accounts")
def konto_hinzufuegen(
    platform: str = Form(...),
    name: str = Form(...),
    external_id: str = Form(""),
):
    from app.services.social_account_service import SocialAccountService
    platform = platform.strip().lower()
    name = name.strip()
    if platform not in {"facebook", "instagram", "x", "tiktok"} or not name:
        return RedirectResponse(url="/settings?account_error=Ungültige Kontodaten", status_code=303)
    SocialAccountService().create(platform=platform, name=name, external_id=external_id)
    return RedirectResponse(url="/settings?account_saved=1", status_code=303)


@router.post("/settings/accounts/{account_id}/toggle")
def konto_umschalten(account_id: str):
    from app.services.social_account_service import SocialAccountService
    SocialAccountService().toggle(account_id)
    return RedirectResponse(url="/settings?account_saved=1", status_code=303)


@router.post("/settings/accounts/{account_id}/delete")
def konto_loeschen(account_id: str):
    from app.services.social_account_service import SocialAccountService
    SocialAccountService().delete(account_id)
    return RedirectResponse(url="/settings?account_deleted=1", status_code=303)
