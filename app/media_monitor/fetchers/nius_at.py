from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from app.media_monitor.fetchers.generic import fetch_homepage_source

SOURCE_NAME = 'NIUS Österreich'
# Absichtlich nur der Österreich-Tag. Der allgemeine NIUS-Newsfeed darf nicht verwendet werden.
DEFAULT_URL = 'https://nius.de/tag/oesterreich'

_EXCLUDED_ROOTS = {
    'tag', 'all-news', 'news', 'shows', 'clips', 'radio', 'autoren', 'abo',
    'shop', 'live-stream', 'nius-live',
}


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix('www.')
    if host != 'nius.de':
        return False
    parts = [part for part in parsed.path.split('/') if part]
    if len(parts) < 2:
        return False
    if parts[0] == 'tag':
        return False
    # Nur konkrete Artikel, die auf der Österreich-Tagseite verlinkt sind.
    # Kategorie-/Navigationsziele werden ausgeschlossen.
    if len(parts) == 2 and parts[0] in _EXCLUDED_ROOTS:
        return False
    return True


def fetch_nius_at(limit: int = 40) -> list[dict[str, Any]]:
    source_url = os.getenv('NIUS_AT_MONITOR_URL', DEFAULT_URL).strip() or DEFAULT_URL
    return fetch_homepage_source(
        source_name=SOURCE_NAME,
        source_url=source_url,
        base_url='https://nius.de/',
        article_url_predicate=_is_article_url,
        limit=limit,
    )
