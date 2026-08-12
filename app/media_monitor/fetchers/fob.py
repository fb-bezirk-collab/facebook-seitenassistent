from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

from app.media_monitor.fetchers.generic import fetch_homepage_source

SOURCE_NAME = 'FoB News'
DEFAULT_URL = 'https://www.fob.at/'

_EXCLUDED = {
    '', 'politik', 'investigativ', 'ai-cyber', 'politischer-islam', 'kommentar',
    'impressum', 'author', 'category', 'tag', 'search',
}


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix('www.')
    if host != 'fob.at':
        return False
    parts = [part for part in parsed.path.split('/') if part]
    if len(parts) != 1:
        return False
    slug = parts[0].lower()
    if slug in _EXCLUDED:
        return False
    return len(slug) >= 12 and '-' in slug and bool(re.search(r'[a-zA-ZäöüÄÖÜß]', slug))


def fetch_fob(limit: int = 40) -> list[dict[str, Any]]:
    source_url = os.getenv('FOB_MONITOR_URL', DEFAULT_URL).strip() or DEFAULT_URL
    return fetch_homepage_source(
        source_name=SOURCE_NAME,
        source_url=source_url,
        base_url='https://www.fob.at/',
        article_url_predicate=_is_article_url,
        limit=limit,
    )
