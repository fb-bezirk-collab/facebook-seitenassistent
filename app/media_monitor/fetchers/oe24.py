from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

import requests

from app.media_monitor.fetchers.common import extract_article_published_at, parse_homepage_articles


SOURCE_NAME = "oe24"
DEFAULT_URL = "https://www.oe24.at/"
REQUEST_TIMEOUT_SECONDS = 25
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Facebook-Seitenassistent/2.1"
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "de-AT,de;q=0.9,en;q=0.5"}


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host != "oe24.at":
        return False
    path = parsed.path.rstrip("/")
    if not path or path in {"/newsticker", "/newsletter"}:
        return False
    # oe24-Artikel enden üblicherweise mit einer numerischen Artikel-ID.
    return bool(re.search(r"(?:-|/)\d{6,}$", path))


def _enrich_published_dates(items: list[dict[str, Any]], session: requests.Session) -> None:
    """Holt nur dann die Artikelseite, wenn auf der Startseite kein Datum vorhanden war."""
    for item in items:
        if item.get("published_at") or not item.get("url"):
            continue
        try:
            response = session.get(str(item["url"]), timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS)
            response.raise_for_status()
            published_at = extract_article_published_at(response.text)
            if published_at:
                item["published_at"] = published_at
        except requests.RequestException as exc:
            # Ein einzelner Artikel darf den gesamten oe24-Abruf nicht blockieren.
            print(f"oe24: Veröffentlichungszeit konnte für {item.get('url')} nicht gelesen werden: {exc}", flush=True)


def fetch_oe24(limit: int = 40) -> list[dict[str, Any]]:
    """Liest aktuelle Artikelverweise von der oe24-Startseite aus."""
    source_url = os.getenv("OE24_MONITOR_URL", DEFAULT_URL).strip() or DEFAULT_URL
    with requests.Session() as session:
        response = session.get(source_url, timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS)
        response.raise_for_status()
        if not response.text.strip():
            raise RuntimeError("oe24.at hat keine Daten geliefert.")
        items = parse_homepage_articles(
            response.text,
            source_name=SOURCE_NAME,
            base_url="https://www.oe24.at/",
            article_url_predicate=_is_article_url,
            limit=max(1, min(limit, 100)),
        )
        if not items:
            raise RuntimeError("Auf oe24.at wurden keine aktuellen Artikel gefunden.")
        _enrich_published_dates(items, session)
        return items
