from __future__ import annotations

import os
from typing import Any

import requests

from app.media_monitor.fetchers.krone import _parse_feed


SOURCE_NAME = "Kurier"
DEFAULT_RSS_URL = "https://kurier.at/xml/rssd"
REQUEST_TIMEOUT_SECONDS = 25
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Facebook-Seitenassistent/2.1"


def fetch_kurier(limit: int = 40) -> list[dict[str, Any]]:
    """Ruft aktuelle KURIER-Meldungen über den offiziellen RSS-Feed ab."""
    rss_url = os.getenv("KURIER_RSS_URL", DEFAULT_RSS_URL).strip() or DEFAULT_RSS_URL
    response = requests.get(
        rss_url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
            "Accept-Language": "de-AT,de;q=0.9,en;q=0.5",
        },
    )
    response.raise_for_status()
    if not response.content.strip():
        raise RuntimeError("Der Kurier-RSS-Feed hat keine Daten geliefert.")

    response.encoding = response.encoding or "utf-8"
    try:
        items = _parse_feed(response.text, limit=max(1, min(limit, 100)))
    except Exception as exc:
        raise RuntimeError("Der Kurier-RSS-Feed konnte nicht gelesen werden.") from exc

    for item in items:
        item["source"] = SOURCE_NAME
        url = str(item.get("url", ""))
        if url.startswith("https://www.krone.at/"):
            item["url"] = url.replace("https://www.krone.at/", "https://kurier.at/", 1)
    if not items:
        raise RuntimeError("Im Kurier-RSS-Feed wurden keine Meldungen gefunden.")
    return items
