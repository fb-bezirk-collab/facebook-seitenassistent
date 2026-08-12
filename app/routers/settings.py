import os
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.models.platform import (
    PLATFORM_DEFINITIONS,
    get_platform,
)
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
from app.services.social_account_service import (
    SocialAccountService,
)
from app.services.instagram_account_service import InstagramAccountService
from app.services.instagram_api import InstagramApiError, InstagramApiService
from app.services.instagram_config_service import load_instagram_config
from app.media_monitor.social_profile import (
    load_social_media_profile,
    load_default_social_media_profile,
    save_social_media_profile,
    reset_social_media_profile,
)


router = APIRouter()
templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR)
)

settings_service = SettingsService()
meta_config_service = MetaConfigService()
social_account_service = SocialAccountService()


@router.get("/settings")
def einstellungen(
    request: Request,
    connected: bool = False,
    facebook_error: str | None = None,
    account_saved: int = 0,
    account_deleted: int = 0,
    account_error: str | None = None,
    instagram_connected: int = 0,
    instagram_count: int = 0,
    instagram_warning: str | None = None,
    social_profile_saved: int = 0,
    social_profile_reset: int = 0,
    social_profile_error: str | None = None,
):
    meta_config = meta_config_service.load()
    facebook_pages = settings_service.load_pages()
    accounts = social_account_service.list_accounts()
    grouped_accounts = (
        social_account_service.grouped_accounts()
    )

    platform_sections = []

    for definition in PLATFORM_DEFINITIONS:
        platform_accounts = grouped_accounts.get(
            definition.id,
            [],
        )

        platform_sections.append({
            "definition": definition,
            "accounts": platform_accounts,
            "active_count": len([
                account
                for account in platform_accounts
                if account.active
            ]),
            "connected_count": len([
                account
                for account in platform_accounts
                if account.is_connected
            ]),
        })

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
            "social_accounts": accounts,
            "platform_sections": platform_sections,
            "platform_definitions": (
                PLATFORM_DEFINITIONS
            ),
            "account_saved": bool(account_saved),
            "account_deleted": bool(
                account_deleted
            ),
            "account_error": account_error,
"instagram_connected": bool(instagram_connected),
"instagram_is_configured": load_instagram_config().is_configured,
"instagram_is_connected": bool(InstagramAccountService().list_accounts()),
            "instagram_count": instagram_count,
            "instagram_warning": instagram_warning,
            "fpoe_social_media_profile": load_social_media_profile(),
            "social_profile_saved": bool(social_profile_saved),
            "social_profile_reset": bool(social_profile_reset),
            "social_profile_error": social_profile_error,
        },
    )


@router.post("/settings/fpoe-social-profile")
def fpoe_social_media_profil_speichern(profile_text: str = Form(...)):
    try:
        save_social_media_profile(profile_text)
    except (OSError, ValueError) as exc:
        return RedirectResponse(
            url="/settings?social_profile_error=" + quote(str(exc)),
            status_code=303,
        )
    return RedirectResponse(url="/settings?social_profile_saved=1", status_code=303)


@router.post("/settings/fpoe-social-profile/reset")
def fpoe_social_media_profil_zuruecksetzen():
    try:
        reset_social_media_profile()
    except OSError as exc:
        return RedirectResponse(
            url="/settings?social_profile_error=" + quote(str(exc)),
            status_code=303,
        )
    return RedirectResponse(url="/settings?social_profile_reset=1", status_code=303)


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

        missing_permissions = (
            facebook_api.missing_required_page_permissions(
                final_token.access_token
            )
        )
        if missing_permissions:
            missing_text = ", ".join(missing_permissions)
            raise FacebookApiError(
                "Die Facebook-Anmeldung wurde abgeschlossen, aber Meta hat "
                "nicht alle erforderlichen Seitenberechtigungen in das Token "
                "übernommen. Es fehlen: " + missing_text + ". "
                "Da diese App Facebook Login for Business mit META_CONFIG_ID "
                "verwendet, müssen diese Rechte in der zugehörigen Meta-"
                "Konfiguration unter Facebook Login for Business → "
                "Configurations/Berechtigungen aktiviert werden. "
                "Danach bitte Meta in den Einstellungen erneut verbinden."
            )

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

        instagram_accounts, instagram_warnings = (
            facebook_api.get_instagram_accounts(pages)
        )
        social_account_service.sync_meta_instagram_accounts(
            instagram_accounts
        )

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

    target = (
        "/settings?connected=true"
        f"&instagram_count={len(instagram_accounts)}"
    )

    if instagram_warnings:
        target += (
            "&instagram_warning="
            + quote(instagram_warnings[0])
        )

    response = RedirectResponse(
        url=target,
        status_code=303,
    )

    response.delete_cookie(
        "facebook_oauth_state"
    )

    return response




@router.get("/instagram/connect")
def instagram_verbinden():
    config = load_instagram_config()
    if not config.is_configured:
        return RedirectResponse(
            url="/settings?account_error=" + quote(
                "Instagram-App ist nicht vollständig konfiguriert."
            ),
            status_code=303,
        )
    state = secrets.token_urlsafe(32)
    try:
        url = InstagramApiService(config).build_login_url(state)
    except InstagramApiError as error:
        return RedirectResponse(
            url="/settings?account_error=" + quote(str(error)),
            status_code=303,
        )
    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(
        "instagram_oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=bool(os.getenv("RAILWAY_ENVIRONMENT")),
        samesite="lax",
    )
    return response


@router.get("/instagram/callback")
def instagram_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    if error:
        return RedirectResponse(
            url="/settings?account_error=" + quote(error_description or error),
            status_code=303,
        )
    saved_state = request.cookies.get("instagram_oauth_state")
    if not state or not saved_state or not secrets.compare_digest(state, saved_state):
        return RedirectResponse(
            url="/settings?account_error=" + quote(
                "Die Sicherheitsprüfung des Instagram-Logins ist fehlgeschlagen."
            ),
            status_code=303,
        )
    if not code:
        return RedirectResponse(
            url="/settings?account_error=" + quote(
                "Instagram hat keinen Anmeldecode zurückgegeben."
            ),
            status_code=303,
        )
    try:
        config = load_instagram_config()
        api = InstagramApiService(config)
        short_token = api.exchange_code(code)
        token, expires_at = api.exchange_long_lived(short_token)
        account = api.get_profile(token, expires_at)
        InstagramAccountService().upsert(account)
    except InstagramApiError as error:
        return RedirectResponse(
            url="/settings?account_error=" + quote(str(error)),
            status_code=303,
        )
    response = RedirectResponse(
        url="/settings?instagram_connected=1",
        status_code=303,
    )
    response.delete_cookie("instagram_oauth_state")
    return response


@router.post("/settings/accounts")
def konto_hinzufuegen(
    platform: str = Form(...),
    name: str = Form(...),
    external_id: str = Form(""),
    username: str = Form(""),
):
    try:
        social_account_service.create(
            platform=platform,
            name=name,
            external_id=external_id,
            username=username,
        )
    except ValueError as error:
        return RedirectResponse(
            url=(
                "/settings?account_error="
                + quote(str(error))
            ),
            status_code=303,
        )

    return RedirectResponse(
        url="/settings?account_saved=1",
        status_code=303,
    )


@router.post(
    "/settings/accounts/{account_id}/toggle"
)
def konto_umschalten(
    account_id: str,
):
    social_account_service.toggle(account_id)

    return RedirectResponse(
        url="/settings?account_saved=1",
        status_code=303,
    )


@router.post(
    "/settings/accounts/{account_id}/delete"
)
def konto_loeschen(
    account_id: str,
):
    social_account_service.delete(account_id)

    return RedirectResponse(
        url="/settings?account_deleted=1",
        status_code=303,
    )
