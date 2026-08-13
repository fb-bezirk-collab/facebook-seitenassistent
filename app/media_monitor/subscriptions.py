from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from cryptography.fernet import Fernet, InvalidToken
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.auth import get_auth_settings
from app.config import MEDIA_SUBSCRIPTIONS_FILE, NOEN_PLAYWRIGHT_PROFILE_DIR
from app.media_monitor.fetchers.generic import HEADERS, response_text


class SubscriptionError(RuntimeError):
    pass


AUTO_SESSION_MAX_AGE = timedelta(hours=6)
NOEN_DEFAULT_URL = "https://www.noen.at/"


@dataclass(frozen=True)
class SubscriptionStatus:
    configured: bool
    saved_at: str = ""
    cookie_count: int = 0
    credentials_configured: bool = False
    automatic_session: bool = False
    mode: str = ""


def _fernet() -> Fernet:
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


def _credentials() -> tuple[str, str]:
    return os.getenv("NOEN_USERNAME", "").strip(), os.getenv("NOEN_PASSWORD", "").strip()


def noen_credentials_configured() -> bool:
    username, password = _credentials()
    return bool(username and password)


def _provider() -> dict:
    value = _read_store().get("noen")
    return value if isinstance(value, dict) else {}


def _automatic_cookies() -> list[dict]:
    raw = _provider().get("automatic_cookies")
    if not isinstance(raw, list):
        return []
    result: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "")
        domain = str(item.get("domain") or "").strip()
        path = str(item.get("path") or "/") or "/"
        if name and domain:
            result.append({"name": name, "value": value, "domain": domain, "path": path})
    return result


def _automatic_session_is_fresh() -> bool:
    saved_at = str(_provider().get("automatic_saved_at") or "").strip()
    if not saved_at:
        return False
    try:
        dt = datetime.fromisoformat(saved_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - dt <= AUTO_SESSION_MAX_AGE


def get_noen_status() -> SubscriptionStatus:
    provider = _provider()
    automatic = _automatic_cookies()
    legacy = _parse_cookie_header(str(provider.get("cookie_header") or ""))
    credentials = noen_credentials_configured()
    if automatic:
        mode = "automatisch"
        saved_at = str(provider.get("automatic_saved_at") or "")
        count = len(automatic)
    elif legacy:
        mode = "cookie-fallback"
        saved_at = str(provider.get("saved_at") or "")
        count = len(legacy)
    elif credentials:
        mode = "zugangsdaten"
        saved_at = ""
        count = 0
    else:
        mode = ""
        saved_at = ""
        count = 0
    return SubscriptionStatus(
        configured=bool(automatic or legacy or credentials),
        saved_at=saved_at,
        cookie_count=count,
        credentials_configured=credentials,
        automatic_session=bool(automatic),
        mode=mode,
    )


def save_noen_cookie(cookie_header: str) -> SubscriptionStatus:
    """Legacy-Fallback aus 3.1.0; wird in der Oberfläche nicht mehr angeboten."""
    header = (cookie_header or "").strip()
    cookies = _parse_cookie_header(header)
    if not cookies:
        raise SubscriptionError(
            "Es wurde kein gültiger Cookie-Header erkannt. Erwartet wird z. B. name=wert; name2=wert2."
        )
    data = _read_store()
    data["noen"] = {
        **(data.get("noen") if isinstance(data.get("noen"), dict) else {}),
        "cookie_header": header,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_store(data)
    return get_noen_status()


def delete_noen_cookie() -> None:
    data = _read_store()
    provider = data.get("noen") if isinstance(data.get("noen"), dict) else {}
    provider.pop("cookie_header", None)
    provider.pop("saved_at", None)
    provider.pop("automatic_cookies", None)
    provider.pop("automatic_saved_at", None)
    provider.pop("automatic_login_url", None)
    provider.pop("automatic_login_note", None)
    if provider:
        data["noen"] = provider
    else:
        data.pop("noen", None)
    if data:
        _write_store(data)
    else:
        try:
            MEDIA_SUBSCRIPTIONS_FILE.unlink()
        except FileNotFoundError:
            pass


def noen_cookie_dict() -> dict[str, str]:
    provider = _provider()
    return _parse_cookie_header(str(provider.get("cookie_header") or ""))


def is_noen_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return False
    return host == "noen.at" or host.endswith(".noen.at")


def _session_from_cookies(cookie_items: list[dict]) -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    for item in cookie_items:
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "")
        domain = str(item.get("domain") or ".noen.at").strip() or ".noen.at"
        path = str(item.get("path") or "/") or "/"
        if name:
            session.cookies.set(name, value, domain=domain, path=path)
    return session


def _session_from_legacy_cookie() -> requests.Session | None:
    cookies = noen_cookie_dict()
    if not cookies:
        return None
    session = requests.Session()
    session.headers.update(HEADERS)
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".noen.at", path="/")
    return session


def _locator_fill_first(frame, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        try:
            locator = frame.locator(selector).first
            if locator.count() and locator.is_visible(timeout=800):
                locator.fill(value, timeout=3_000)
                return True
        except Exception:
            continue
    return False


def _click_login_trigger(page) -> bool:
    text_patterns = [
        re.compile(r"^\s*Mein\s+Konto\s*$", re.I),
        re.compile(r"^\s*Anmelden\s*$", re.I),
        re.compile(r"^\s*Einloggen\s*$", re.I),
        re.compile(r"^\s*Login\s*$", re.I),
    ]
    for pattern in text_patterns:
        try:
            locator = page.get_by_text(pattern).first
            if locator.count() and locator.is_visible(timeout=800):
                locator.click(timeout=5_000)
                return True
        except Exception:
            continue
    for selector in [
        "a[href*='login' i]",
        "a[href*='account' i]",
        "button[id*='login' i]",
        "button[class*='login' i]",
    ]:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible(timeout=800):
                locator.click(timeout=5_000)
                return True
        except Exception:
            continue
    return False


def _login_form_frame(page):
    password_selectors = [
        "input[type='password']",
        "input[name*='password' i]",
        "input[id*='password' i]",
    ]
    for frame in page.frames:
        for selector in password_selectors:
            try:
                locator = frame.locator(selector).first
                if locator.count() and locator.is_visible(timeout=700):
                    return frame
            except Exception:
                continue
    return None


def _looks_logged_in(page) -> bool:
    try:
        body_class = page.locator("body").get_attribute("class") or ""
        if "user-logged-in" in body_class.lower():
            return True
    except Exception:
        pass
    for pattern in [r"Abmelden", r"Logout", r"Mein\s+Konto"]:
        try:
            locator = page.get_by_text(re.compile(pattern, re.I)).first
            if locator.count() and locator.is_visible(timeout=600):
                # "Mein Konto" kann auch im ausgeloggten Zustand sichtbar sein;
                # zusammen mit fehlendem Passwortfeld ist es trotzdem ein brauchbarer Hinweis.
                if "konto" not in pattern.lower() or _login_form_frame(page) is None:
                    return True
        except Exception:
            continue
    return False


def refresh_noen_login(*, force: bool = True) -> dict[str, object]:
    username, password = _credentials()
    if not username or not password:
        raise SubscriptionError(
            "NOEN_USERNAME und NOEN_PASSWORD sind in Railway noch nicht vollständig gesetzt."
        )

    if not force and _automatic_cookies() and _automatic_session_is_fresh():
        return {
            "ok": True,
            "reused": True,
            "cookie_count": len(_automatic_cookies()),
            "message": "Vorhandene automatische NÖN-Sitzung wird weiterverwendet.",
        }

    login_url = os.getenv("NOEN_LOGIN_URL", "").strip() or NOEN_DEFAULT_URL
    NOEN_PLAYWRIGHT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(NOEN_PLAYWRIGHT_PROFILE_DIR),
                headless=True,
                viewport={"width": 1440, "height": 1100},
                args=["--disable-dev-shm-usage"],
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(5_000)
                page.goto(login_url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(2_000)

                if not _looks_logged_in(page):
                    _click_login_trigger(page)
                    page.wait_for_timeout(2_000)

                    # Manche Login-Buttons öffnen ein neues Fenster / eine neue Seite.
                    if context.pages:
                        page = context.pages[-1]

                    frame = _login_form_frame(page)
                    if frame is None:
                        raise SubscriptionError(
                            "Der NÖN-Login wurde geöffnet, aber es konnte kein Passwortfeld gefunden werden. "
                            "Falls NÖN den Login geändert hat, kann optional NOEN_LOGIN_URL in Railway auf die konkrete Login-Seite gesetzt werden."
                        )

                    email_ok = _locator_fill_first(
                        frame,
                        [
                            "input[type='email']",
                            "input[name*='email' i]",
                            "input[id*='email' i]",
                            "input[name*='user' i]",
                            "input[id*='user' i]",
                            "input[autocomplete='username']",
                        ],
                        username,
                    )
                    password_ok = _locator_fill_first(
                        frame,
                        [
                            "input[type='password']",
                            "input[name*='password' i]",
                            "input[id*='password' i]",
                            "input[autocomplete='current-password']",
                        ],
                        password,
                    )
                    if not email_ok or not password_ok:
                        raise SubscriptionError(
                            "Das NÖN-Loginformular wurde gefunden, aber Benutzername oder Passwortfeld konnten nicht automatisch befüllt werden."
                        )

                    submitted = False

                    # 1) Klassische Buttons nach sichtbarer Beschriftung.
                    for pattern in [r"Anmelden", r"Einloggen", r"Login", r"Weiter", r"Fortfahren", r"Bestätigen"]:
                        try:
                            button = frame.get_by_role("button", name=re.compile(pattern, re.I)).first
                            if button.count() and button.is_visible(timeout=700):
                                button.click(timeout=5_000)
                                submitted = True
                                break
                        except Exception:
                            continue

                    # 2) Normale Submit-Controls, auch wenn sie keine passende Beschriftung haben.
                    if not submitted:
                        for selector in [
                            "button[type='submit']",
                            "input[type='submit']",
                            "button[name*='login' i]",
                            "button[id*='login' i]",
                            "button[class*='login' i]",
                            "a[role='button'][href*='login' i]",
                        ]:
                            try:
                                button = frame.locator(selector).first
                                if button.count() and button.is_visible(timeout=700):
                                    button.click(timeout=5_000)
                                    submitted = True
                                    break
                            except Exception:
                                continue

                    # 3) Viele moderne Login-Komponenten senden per Enter ab und besitzen
                    #    keinen klassischen submit-Button im DOM.
                    if not submitted:
                        for selector in [
                            "input[type='password']",
                            "input[name*='password' i]",
                            "input[id*='password' i]",
                            "input[autocomplete='current-password']",
                        ]:
                            try:
                                password_field = frame.locator(selector).first
                                if password_field.count() and password_field.is_visible(timeout=700):
                                    password_field.press("Enter", timeout=5_000)
                                    submitted = True
                                    break
                            except Exception:
                                continue

                    # 4) Letzter sauberer Fallback: das Formular des Passwortfeldes über
                    #    requestSubmit() absenden. Dadurch werden normale submit-Handler
                    #    und Browser-Validierung ausgelöst, statt das Formular blind zu posten.
                    if not submitted:
                        try:
                            result = frame.evaluate(
                                """
                                () => {
                                  const pw = document.querySelector(
                                    'input[type="password"], input[name*="password" i], input[id*="password" i], input[autocomplete="current-password"]'
                                  );
                                  if (!pw) return false;
                                  const form = pw.closest('form');
                                  if (!form) return false;
                                  if (typeof form.requestSubmit === 'function') form.requestSubmit();
                                  else form.submit();
                                  return true;
                                }
                                """
                            )
                            submitted = bool(result)
                        except Exception:
                            submitted = False

                    if not submitted:
                        raise SubscriptionError(
                            "Der NÖN-Login konnte trotz befüllter Zugangsdaten nicht abgesendet werden. "
                            "NÖN verwendet offenbar einen ungewöhnlichen Login-Ablauf."
                        )

                    page.wait_for_timeout(6_000)
                    try:
                        page.goto(NOEN_DEFAULT_URL, wait_until="domcontentloaded", timeout=60_000)
                        page.wait_for_timeout(2_000)
                    except Exception:
                        pass

                if not _looks_logged_in(page):
                    raise SubscriptionError(
                        "NÖN hat den automatischen Login nicht als angemeldet bestätigt. "
                        "Bitte Zugangsdaten prüfen; falls Captcha/2FA erscheint, ist ein rein automatischer Login nicht möglich."
                    )

                cookies = context.cookies()
                relevant = [
                    {
                        "name": c.get("name", ""),
                        "value": c.get("value", ""),
                        "domain": c.get("domain", ""),
                        "path": c.get("path", "/") or "/",
                    }
                    for c in cookies
                    if "noen.at" in str(c.get("domain") or "").lower()
                ]
                if not relevant:
                    # Falls der Login über einen externen Identity-Provider läuft,
                    # bewahren wir notfalls alle Cookies auf; beim requests-Transfer
                    # werden nur Domain-passende Cookies an NÖN gesendet.
                    relevant = [
                        {
                            "name": c.get("name", ""),
                            "value": c.get("value", ""),
                            "domain": c.get("domain", ""),
                            "path": c.get("path", "/") or "/",
                        }
                        for c in cookies
                        if c.get("name") and c.get("domain")
                    ]
            finally:
                context.close()
    except SubscriptionError:
        raise
    except PlaywrightTimeoutError as exc:
        raise SubscriptionError(f"NÖN-Login hat zu lange gedauert: {exc}") from exc
    except Exception as exc:
        raise SubscriptionError(f"Automatischer NÖN-Login fehlgeschlagen: {exc}") from exc

    data = _read_store()
    provider = data.get("noen") if isinstance(data.get("noen"), dict) else {}
    provider["automatic_cookies"] = relevant
    provider["automatic_saved_at"] = datetime.now(timezone.utc).isoformat()
    provider["automatic_login_url"] = login_url
    provider["automatic_login_note"] = "Login über NOEN_USERNAME/NOEN_PASSWORD"
    data["noen"] = provider
    _write_store(data)

    return {
        "ok": True,
        "reused": False,
        "cookie_count": len(relevant),
        "message": "Automatischer NÖN-Login erfolgreich.",
    }


def build_noen_session() -> requests.Session | None:
    # Primär: Railway-Zugangsdaten. Frische automatische Sitzung wiederverwenden,
    # ansonsten einmal neu anmelden. Fehler dürfen die Medienanalyse nicht stoppen.
    if noen_credentials_configured():
        try:
            if not _automatic_cookies() or not _automatic_session_is_fresh():
                refresh_noen_login(force=True)
            cookies = _automatic_cookies()
            if cookies:
                return _session_from_cookies(cookies)
        except SubscriptionError:
            pass

    # Fallback für bereits hinterlegte Cookie-Sitzungen aus Version 3.1.0.
    automatic = _automatic_cookies()
    if automatic:
        return _session_from_cookies(automatic)
    return _session_from_legacy_cookie()


def _visible_text_size(page: str) -> int:
    from html import unescape

    cleaned = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\\1>", " ", page or "")
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\\s+", " ", cleaned).strip()
    return len(cleaned)


def test_noen_subscription(url: str, *, force_login: bool = False) -> dict[str, object]:
    target = (url or "").strip()
    if not target or not is_noen_url(target):
        raise SubscriptionError("Bitte eine vollständige noen.at-Artikel-URL eintragen.")

    # 3.1.3: Eine bereits gespeicherte, frische Sitzung hat immer Vorrang.
    # Ein neuer Browser-Login wird nur aufgebaut, wenn keine verwendbare Sitzung
    # vorhanden ist bzw. ausdrücklich erzwungen wurde UND keine frische Session existiert.
    login_result: dict[str, object] | None = None
    reused_saved_session = bool(_automatic_cookies() and _automatic_session_is_fresh())

    if noen_credentials_configured() and not reused_saved_session:
        login_result = refresh_noen_login(force=True)
    elif force_login and noen_credentials_configured() and not _automatic_cookies():
        login_result = refresh_noen_login(force=True)

    session = build_noen_session()
    if session is None:
        if noen_credentials_configured():
            raise SubscriptionError("Der automatische NÖN-Login konnte keine verwendbare Sitzung erzeugen.")
        raise SubscriptionError(
            "Es sind weder NOEN_USERNAME/NOEN_PASSWORD in Railway noch eine ältere Cookie-Sitzung hinterlegt."
        )

    def fetch_with_session(active_session: requests.Session):
        try:
            response = active_session.get(target, timeout=30, allow_redirects=True)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise SubscriptionError(f"NÖN-Testabruf fehlgeschlagen: {exc}") from exc

    try:
        public_response = requests.get(target, headers=HEADERS, timeout=30, allow_redirects=True)
    except requests.RequestException as exc:
        raise SubscriptionError(f"Öffentlicher NÖN-Testabruf fehlgeschlagen: {exc}") from exc

    auth_response = fetch_with_session(session)
    public_page = response_text(public_response) if public_response.ok else ""
    auth_page = response_text(auth_response)

    # Wenn eine ältere gespeicherte Sitzung offensichtlich auf eine Login-Seite
    # umleitet, versuchen wir genau einmal eine echte Erneuerung über Railway.
    final_lower = str(auth_response.url or "").lower()
    looks_like_login_redirect = any(part in final_lower for part in ("login", "signin", "anmelden"))
    if looks_like_login_redirect and noen_credentials_configured():
        login_result = refresh_noen_login(force=True)
        session = build_noen_session()
        if session is None:
            raise SubscriptionError("Die NÖN-Sitzung konnte nach dem erneuten Login nicht aufgebaut werden.")
        auth_response = fetch_with_session(session)
        auth_page = response_text(auth_response)
        reused_saved_session = False

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
        "cookie_count": len(session.cookies),
        "credentials_configured": noen_credentials_configured(),
        "automatic_session": bool(_automatic_cookies()),
        "reused_saved_session": reused_saved_session,
        "login_result": login_result,
    }
