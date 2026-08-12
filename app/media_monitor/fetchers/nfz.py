from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from app.media_monitor.fetchers.generic import fetch_homepage_source

SOURCE_NAME = 'NFZ'
DEFAULT_URL = 'https://www.nfz.at/'


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix('www.')
    if host != 'nfz.at':
        return False
    parts = [part for part in parsed.path.split('/') if part]
    return len(parts) >= 3 and parts[0] == 'news' and parts[1] == 'artikel-detailansicht' and bool(parts[2])


def fetch_nfz(limit: int = 40) -> list[dict[str, Any]]:
    source_url = os.getenv('NFZ_MONITOR_URL', DEFAULT_URL).strip() or DEFAULT_URL
    return fetch_homepage_source(
        source_name=SOURCE_NAME,
        source_url=source_url,
        base_url='https://www.nfz.at/',
        article_url_predicate=_is_article_url,
        limit=limit,
    )
