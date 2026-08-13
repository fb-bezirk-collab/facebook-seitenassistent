from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from cryptography.fernet import Fernet, InvalidToken

from app.auth import get_auth_settings
from app.config import MEDIA_SUBSCRIPTIONS_FILE
from app.media_monitor.fetchers.generic import HEADERS, response_text


class SubscriptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SubscriptionStatus:
    configured: bool
    saved_at: str = ""
    cookie_count: int = 0


def _fernet() -> Fernet:
    # Optional kann später MEDIA_SESSION_SECRET ergänzt werden. Für den Pilot
    # wird der bereits vorhandene Session-Schlüssel der App verwendet und zu
    # einem separaten Fernet-Key abgeleitet.
    secret = os.getenv("MEDIA_SESSION_SECRET", "").strip() or get_auth_settings().session_secret
    digest = hashlib.sha256(("media-subscriptions:" + secret).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _read_store() -> dict:
    try:
        raw = MEDIA_SUBSCRIPTIONS_FILE.read_bytes()
    except OSError:
        return {}
    if not raw:
        return {}
    try:
        decoded = _fernet().decrypt(raw)
        value = json.loads(decoded.decode("utf-8"))
    except (InvalidToken, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_store(data: dict) -> None:
    MEDIA_SUBSCRIPTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    MEDIA_SUBSCRIPTIONS_FILE.write_bytes(_fernet().encrypt(payload))


def _parse_cookie_header(cookie_header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in (cookie_header or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            cookies[name] = value
    return cookies


def get_noen_status() -> SubscriptionStatus:
    provider = _read_store().get("noen")
    if not isinstance(provider, dict):
        return SubscriptionStatus(False)
    header = str(provider.get("cookie_header") or "")
    cookies = _parse_cookie_header(header)
    return SubscriptionStatus(
        configured=bool(cookies),
        saved_at=str(provider.get("saved_at") or ""),
        cookie_count=len(cookies),
    )


def save_noen_cookie(cookie_header: str) -> SubscriptionStatus:
    header = (cookie_header or "").strip()
    cookies = _parse_cookie_header(header)
    if not cookies:
        raise SubscriptionError(
            "Es wurde kein gültiger Cookie-Header erkannt. Erwartet wird z. B. name=wert; name2=wert2."
        )
    data = _read_store()
    data["noen"] = {
        "cookie_header": header,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_store(data)
    return get_noen_status()


def delete_noen_cookie() -> None:
    data = _read_store()
    data.pop("noen", None)
    if data:
        _write_store(data)
    else:
        try:
            MEDIA_SUBSCRIPTIONS_FILE.unlink()
        except FileNotFoundError:
            pass


def noen_cookie_dict() -> dict[str, str]:
    provider = _read_store().get("noen")
    if not isinstance(provider, dict):
        return {}
    return _parse_cookie_header(str(provider.get("cookie_header") or ""))


def is_noen_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return False
    return host == "noen.at" or host.endswith(".noen.at")


def build_noen_session() -> requests.Session | None:
    cookies = noen_cookie_dict()
    if not cookies:
        return None
    session = requests.Session()
    session.headers.update(HEADERS)
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".noen.at", path="/")
    return session


def _visible_text_size(page: str) -> int:
    # Nur Diagnosewert: HTML-Tags entfernen, Script/Style-Blöcke reduzieren.
    import re
    from html import unescape

    cleaned = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\\1>", " ", page or "")
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\\s+", " ", cleaned).strip()
    return len(cleaned)


def test_noen_subscription(url: str) -> dict[str, object]:
    target = (url or "").strip()
    if not target or not is_noen_url(target):
        raise SubscriptionError("Bitte eine vollständige noen.at-Artikel-URL eintragen.")

    session = build_noen_session()
    if session is None:
        raise SubscriptionError("Es ist noch keine NÖN-Abo-Sitzung hinterlegt.")

    try:
        public_response = requests.get(
            target,
            headers=HEADERS,
            timeout=30,
            allow_redirects=True,
        )
        auth_response = session.get(target, timeout=30, allow_redirects=True)
        auth_response.raise_for_status()
    except requests.RequestException as exc:
        raise SubscriptionError(f"NÖN-Testabruf fehlgeschlagen: {exc}") from exc

    public_page = response_text(public_response) if public_response.ok else ""
    auth_page = response_text(auth_response)
    public_visible = _visible_text_size(public_page)
    auth_visible = _visible_text_size(auth_page)
    gain = max(0, auth_visible - public_visible)

    return {
        "status_code": auth_response.status_code,
        "final_url": auth_response.url,
        "public_visible_chars": public_visible,
        "subscription_visible_chars": auth_visible,
        "visible_gain": gain,
        "content_changed": auth_page != public_page,
        "likely_more_content": gain >= 500,
        "cookie_count": len(noen_cookie_dict()),
    }
