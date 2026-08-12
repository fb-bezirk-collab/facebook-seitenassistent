from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

from app.media_monitor.fetchers.generic import fetch_homepage_source

SOURCE_NAME = 'ZurZeit'
DEFAULT_URL = 'https://zurzeit.at/'

_EXCLUDED_SLUGS = {
    'leserbriefe-2', 'impressum', 'datenschutz', 'kontakt', 'shop', 'abo',
}


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix('www.')
    if host != 'zurzeit.at':
        return False
    parts = [part for part in parsed.path.split('/') if part]
    # ZurZeit nutzt WordPress-artige URLs /index.php/<artikel-slug>/
    if len(parts) != 2 or parts[0].lower() != 'index.php':
        return False
    slug = parts[1].lower()
    if slug in _EXCLUDED_SLUGS:
        return False
    return len(slug) >= 12 and '-' in slug and bool(re.search(r'[a-zA-ZäöüÄÖÜß]', slug))


def fetch_zurzeit(limit: int = 40) -> list[dict[str, Any]]:
    source_url = os.getenv('ZURZEIT_MONITOR_URL', DEFAULT_URL).strip() or DEFAULT_URL
    return fetch_homepage_source(
        source_name=SOURCE_NAME,
        source_url=source_url,
        base_url='https://zurzeit.at/',
        article_url_predicate=_is_article_url,
        limit=limit,
    )
