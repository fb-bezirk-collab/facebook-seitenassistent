from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import requests

from app.media_monitor.fetchers.common import parse_homepage_articles


SOURCE_NAME = "Heute"
DEFAULT_URL = "https://www.heute.at/"
REQUEST_TIMEOUT_SECONDS = 25
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Facebook-Seitenassistent/2.1"


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host != "heute.at":
        return False
    path = parsed.path.rstrip("/")
    return path.startswith("/s/") and len(path.split("/")) >= 3


def fetch_heute(limit: int = 40) -> list[dict[str, Any]]:
    """Liest aktuelle Artikelverweise von der Heute-Startseite aus."""
    source_url = os.getenv("HEUTE_MONITOR_URL", DEFAULT_URL).strip() or DEFAULT_URL
    response = requests.get(
        source_url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "de-AT,de;q=0.9,en;q=0.5"},
    )
    response.raise_for_status()
    if not response.text.strip():
        raise RuntimeError("Heute.at hat keine Daten geliefert.")
    items = parse_homepage_articles(
        response.text,
        source_name=SOURCE_NAME,
        base_url="https://www.heute.at/",
        article_url_predicate=_is_article_url,
        limit=max(1, min(limit, 100)),
    )
    if not items:
        raise RuntimeError("Auf Heute.at wurden keine aktuellen Artikel gefunden.")
    return items
