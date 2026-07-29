import hashlib
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Request


# Lokale Entwicklung: Werte aus einer vorhandenen .env-Datei laden.
# In Railway haben die dort gesetzten Variablen weiterhin Vorrang.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=False)


class AuthConfigurationError(RuntimeError):
    """Die Login-Konfiguration ist unvollständig."""


@dataclass(frozen=True)
class AuthSettings:
    username: str
    password: str
    session_secret: str
    secure_cookie: bool


def _read_env(name: str, default: str = "") -> str:
    """Liest Umgebungsvariablen robust und ohne Probleme durch Leerzeichen."""
    direct_value = os.getenv(name)
    if direct_value is not None:
        return direct_value.strip()

    # Zusätzliche Absicherung gegen versehentlich anders geschriebene Variablennamen.
    wanted = name.casefold()
    for key, value in os.environ.items():
        if key.strip().casefold() == wanted:
            return value.strip()

    return default


def _configured_username() -> str:
    return _read_env("ADMIN_USERNAME", "admin") or "admin"


def _configured_password() -> str:
    return _read_env("ADMIN_PASSWORD")


def _configured_session_secret() -> str:
    configured = _read_env("SESSION_SECRET")
    if configured:
        return configured

    # Der Server darf wegen einer fehlenden Variable nicht mehr abstürzen.
    # Ist zumindest das Admin-Passwort vorhanden, wird daraus deterministisch
    # ein nur für die Session-Signatur verwendeter Schlüssel abgeleitet.
    password = _configured_password()
    if password:
        return hashlib.sha256(
            ("facebook-seitenassistent-session:" + password).encode("utf-8")
        ).hexdigest()

    # Letzter Fallback: Die Login-Seite bleibt erreichbar und zeigt eine klare
    # Konfigurationsmeldung. Nach einem Neustart werden bestehende Sessions ungültig.
    return secrets.token_urlsafe(48)


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    return AuthSettings(
        username=_configured_username(),
        password=_configured_password(),
        session_secret=_configured_session_secret(),
        secure_cookie=bool(_read_env("RAILWAY_ENVIRONMENT")),
    )


def validate_auth_configuration() -> None:
    if not get_auth_settings().password:
        raise AuthConfigurationError(
            "ADMIN_PASSWORD ist für diesen Railway-Service nicht verfügbar. "
            "Bitte die Variable unter Service → Variables speichern und anschließend neu deployen."
        )


def verify_credentials(username: str, password: str) -> bool:
    validate_auth_configuration()
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


def auth_status() -> dict[str, bool]:
    """Nur nicht-sensitive Statuswerte für den Healthcheck."""
    settings = get_auth_settings()
    return {
        "admin_username_configured": bool(settings.username),
        "admin_password_configured": bool(settings.password),
        "session_secret_configured": bool(_read_env("SESSION_SECRET")),
    }
