import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass

from fastapi import Request


@dataclass(frozen=True)
class AuthSettings:
    username: str
    password: str
    session_secret: str
    secure_cookie: bool


def get_auth_settings() -> AuthSettings:
    username = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.getenv("ADMIN_PASSWORD", "").strip()
    session_secret = os.getenv("SESSION_SECRET", "").strip()

    if not password:
        raise RuntimeError(
            "ADMIN_PASSWORD fehlt. Bitte in Railway unter Variables festlegen."
        )

    if not session_secret:
        raise RuntimeError(
            "SESSION_SECRET fehlt. Bitte in Railway unter Variables festlegen."
        )

    return AuthSettings(
        username=username,
        password=password,
        session_secret=session_secret,
        secure_cookie=bool(os.getenv("RAILWAY_ENVIRONMENT")),
    )


def verify_credentials(username: str, password: str) -> bool:
    settings = get_auth_settings()
    username_ok = secrets.compare_digest(username.strip(), settings.username)
    password_ok = secrets.compare_digest(password, settings.password)
    return username_ok and password_ok


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def current_username(request: Request) -> str | None:
    if not is_authenticated(request):
        return None
    return str(request.session.get("username") or "") or None
