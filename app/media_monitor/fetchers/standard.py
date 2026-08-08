from __future__ import annotations

import os
from typing import Any

import requests

from app.media_monitor.fetchers.rss import parse_feed

SOURCE_NAME = 'Der Standard'
DEFAULT_RSS_URL = 'https://www.derstandard.at/rss'
REQUEST_TIMEOUT_SECONDS = 25
HEADERS = {'User-Agent': 'Facebook-Seitenassistent/2.2', 'Accept-Language': 'de-AT,de;q=0.9'}


def fetch_standard(limit: int = 40) -> list[dict[str, Any]]:
    url = os.getenv('STANDARD_RSS_URL', DEFAULT_RSS_URL).strip() or DEFAULT_RSS_URL
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS)
    response.raise_for_status()
    try:
        items = parse_feed(response.text, source_name=SOURCE_NAME, base_url='https://www.derstandard.at/', limit=limit)
    except Exception as exc:
        raise RuntimeError('Der Standard-RSS-Feed konnte nicht gelesen werden.') from exc
    if not items:
        raise RuntimeError('Im Standard-RSS-Feed wurden keine Meldungen gefunden.')
    return items
