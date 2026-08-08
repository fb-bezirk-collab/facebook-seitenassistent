from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

from app.media_monitor.fetchers.generic import fetch_homepage_source

SOURCE_NAME = 'exxpress'
DEFAULT_URL = 'https://exxpress.at/'


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix('www.')
    if host != 'exxpress.at':
        return False
    path = parsed.path.rstrip('/')
    if not path or path in {'/news', '/politik', '/wirtschaft', '/lifestyle', '/sport', '/meinung'}:
        return False
    # Artikelseiten haben typischerweise einen sprechenden Slug; reine Ressortseiten werden oben abgefangen.
    return len([part for part in path.split('/') if part]) >= 1 and bool(re.search(r'[a-zA-ZäöüÄÖÜß]', path))


def fetch_exxpress(limit: int = 40) -> list[dict[str, Any]]:
    source_url = os.getenv('EXXPRESS_MONITOR_URL', DEFAULT_URL).strip() or DEFAULT_URL
    return fetch_homepage_source(
        source_name=SOURCE_NAME,
        source_url=source_url,
        base_url='https://exxpress.at/',
        article_url_predicate=_is_article_url,
        limit=limit,
    )
