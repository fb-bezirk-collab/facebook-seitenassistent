from urllib.parse import urlparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import (
    AuthConfigurationError,
    current_username,
    validate_auth_configuration,
    verify_credentials,
)
from app.config import TEMPLATES_DIR


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _safe_next_url(value: str | None) -> str:
    if not value:
        return "/"
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/"):
        return "/"
    return value


def _configuration_error() -> str | None:
    try:
        validate_auth_configuration()
    except AuthConfigurationError as exc:
        return str(exc)
    return None


@router.get("/login", name="login")
def login_form(request: Request, next: str = "/", error: int = 0):
    if current_username(request):
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": bool(error),
            "configuration_error": _configuration_error(),
            "next_url": _safe_next_url(next),
        },
    )


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next_url: str = Form("/"),
):
    target = _safe_next_url(next_url)

    try:
        credentials_valid = verify_credentials(username, password)
    except AuthConfigurationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": False,
                "configuration_error": str(exc),
                "next_url": target,
            },
            status_code=503,
        )

    if not credentials_valid:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": True,
                "configuration_error": None,
                "next_url": target,
            },
            status_code=401,
        )

    request.session.clear()
    request.session["authenticated"] = True
    request.session["username"] = username.strip()

    return RedirectResponse(url=target, status_code=303)


@router.post("/logout", name="logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
