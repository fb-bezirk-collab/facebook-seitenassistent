from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.config import DATA_DIR, NOEN_PLAYWRIGHT_PROFILE_DIR
from app.media_monitor.subscriptions import is_noen_url


JOB_FILE = DATA_DIR / "noen_debug_job.json"
SCREENSHOT_FILE = DATA_DIR / "noen_debug_latest.png"
_LOCK = threading.Lock()
_RUNNING = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_url(value: str) -> str:
    """URL ohne Query/Fragment, damit keine Tokens in der Diagnose landen."""
    try:
        parts = urlsplit(str(value or ""))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except Exception:
        return str(value or "").split("?", 1)[0].split("#", 1)[0]


def _safe_host(value: str) -> str:
    try:
        return urlsplit(str(value or "")).netloc.lower()
    except Exception:
        return ""


def _redact(text: str) -> str:
    value = str(text or "")
    username = os.getenv("NOEN_USERNAME", "").strip()
    if username:
        value = value.replace(username, "[NOEN_USERNAME]")
    value = re.sub(r"(?i)(token|session|cookie|authorization)=([^\s&]+)", r"\1=[REDACTED]", value)
    return value[:600]


def _write(data: dict) -> None:
    JOB_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = JOB_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(JOB_FILE)


def get_noen_debug_job() -> dict:
    try:
        raw = json.loads(JOB_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def screenshot_available() -> bool:
    return SCREENSHOT_FILE.exists() and SCREENSHOT_FILE.is_file()


def _body_info(page) -> dict:
    try:
        body_text = page.locator("body").inner_text(timeout=2_500)
    except Exception:
        body_text = ""
    try:
        body_class = page.locator("body").get_attribute("class") or ""
    except Exception:
        body_class = ""

    lower = body_text.lower()
    paywall_words = [
        "abo", "abonn", "registrieren", "jetzt weiterlesen", "weiterlesen",
        "premium", "plus-artikel", "bezahl", "anmelden", "einloggen",
    ]
    paywall_hits = [word for word in paywall_words if word in lower]

    password_visible = False
    try:
        for frame in page.frames:
            loc = frame.locator("input[type='password']").first
            if loc.count() and loc.is_visible(timeout=300):
                password_visible = True
                break
    except Exception:
        pass

    article_selectors = [
        "article",
        "[itemprop='articleBody']",
        "[class*='article-body' i]",
        "[class*='article__body' i]",
        "[class*='article-content' i]",
        "[class*='story-content' i]",
        "main",
    ]
    selector_sizes: dict[str, int] = {}
    for selector in article_selectors:
        try:
            loc = page.locator(selector).first
            if loc.count():
                text = loc.inner_text(timeout=1_000)
                if text.strip():
                    selector_sizes[selector] = len(text.strip())
        except Exception:
            continue

    return {
        "visible_chars": len(body_text.strip()),
        "body_user_logged_in_class": "user-logged-in" in body_class.lower(),
        "password_field_visible": password_visible,
        "paywall_markers": paywall_hits[:12],
        "article_selector_chars": selector_sizes,
    }


def _run(url: str) -> None:
    global _RUNNING
    failures: list[dict] = []
    http_errors: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    hosts: set[str] = set()

    try:
        SCREENSHOT_FILE.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass

    job = {
        "status": "running",
        "started_at": _now(),
        "finished_at": "",
        "article_url": _safe_url(url),
        "steps": [],
        "failures": failures,
        "http_errors": http_errors,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "hosts": [],
        "error": "",
        "screenshot_available": False,
    }
    _write(job)

    try:
        NOEN_PLAYWRIGHT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
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

                def on_request(req):
                    host = _safe_host(req.url)
                    if host:
                        hosts.add(host)

                def on_failed(req):
                    if len(failures) >= 40:
                        return
                    failures.append({
                        "method": req.method,
                        "url": _safe_url(req.url),
                        "error": _redact(str(req.failure or "request failed")),
                    })

                def on_response(resp):
                    if resp.status < 400 or len(http_errors) >= 60:
                        return
                    http_errors.append({
                        "status": resp.status,
                        "url": _safe_url(resp.url),
                    })

                def on_console(msg):
                    if msg.type == "error" and len(console_errors) < 30:
                        console_errors.append(_redact(msg.text))

                def on_page_error(exc):
                    if len(page_errors) < 30:
                        page_errors.append(_redact(str(exc)))

                page.on("request", on_request)
                page.on("requestfailed", on_failed)
                page.on("response", on_response)
                page.on("console", on_console)
                page.on("pageerror", on_page_error)

                response = None
                navigation_error = ""
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                except PlaywrightTimeoutError as exc:
                    navigation_error = f"Navigation-Timeout nach 20 Sekunden: {_redact(str(exc))}"
                except Exception as exc:
                    navigation_error = f"Navigation-Fehler: {_redact(str(exc))}"

                for seconds in (0, 5, 10, 20):
                    if seconds:
                        page.wait_for_timeout((seconds - (0 if seconds == 5 else 5 if seconds == 10 else 10)) * 1000)
                    info = _body_info(page)
                    info.update({
                        "after_seconds": seconds,
                        "url": _safe_url(page.url),
                        "title": _redact(page.title()),
                    })
                    job["steps"].append(info)
                    job["hosts"] = sorted(hosts)
                    job["navigation_status"] = response.status if response is not None else None
                    job["navigation_error"] = navigation_error
                    _write(job)

                try:
                    SCREENSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(SCREENSHOT_FILE), full_page=True, timeout=10_000)
                    job["screenshot_available"] = True
                except Exception as exc:
                    job["screenshot_error"] = _redact(str(exc))

                job["final_url"] = _safe_url(page.url)
                job["final_title"] = _redact(page.title())
                job["cookie_count_browser"] = len(context.cookies())
            finally:
                context.close()

        job["status"] = "done"
        job["finished_at"] = _now()
        job["hosts"] = sorted(hosts)
        _write(job)
    except Exception as exc:
        job["status"] = "error"
        job["finished_at"] = _now()
        job["error"] = _redact(str(exc))
        job["hosts"] = sorted(hosts)
        _write(job)
    finally:
        with _LOCK:
            _RUNNING = False


def start_noen_debug(url: str) -> dict:
    global _RUNNING
    target = (url or "").strip()
    if not target or not is_noen_url(target):
        raise ValueError("Bitte eine vollständige noen.at-Artikel-URL eintragen.")

    with _LOCK:
        current = get_noen_debug_job()
        stale_running = False
        if current.get("status") == "running" and not _RUNNING:
            try:
                started = datetime.fromisoformat(str(current.get("started_at") or ""))
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                stale_running = (datetime.now(timezone.utc) - started).total_seconds() > 180
            except Exception:
                stale_running = True
        if _RUNNING or (current.get("status") == "running" and not stale_running):
            return {"started": False, "message": "Eine NÖN-Diagnose läuft bereits."}
        _RUNNING = True

    thread = threading.Thread(target=_run, args=(target,), daemon=True, name="noen-debug")
    thread.start()
    return {"started": True, "message": "NÖN-Diagnose wurde gestartet."}
