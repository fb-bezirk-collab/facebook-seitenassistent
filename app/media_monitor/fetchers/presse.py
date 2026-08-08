from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from app.media_monitor.fetchers.generic import fetch_homepage_source

SOURCE_NAME = 'Die Presse'
DEFAULT_URL = 'https://www.diepresse.com/'


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix('www.')
    if host != 'diepresse.com':
        return False
    parts = [part for part in parsed.path.split('/') if part]
    return bool(parts and parts[0].isdigit() and len(parts[0]) >= 5)


def fetch_presse(limit: int = 40) -> list[dict[str, Any]]:
    source_url = os.getenv('PRESSE_MONITOR_URL', DEFAULT_URL).strip() or DEFAULT_URL
    return fetch_homepage_source(
        source_name=SOURCE_NAME,
        source_url=source_url,
        base_url='https://www.diepresse.com/',
        article_url_predicate=_is_article_url,
        limit=limit,
    )
