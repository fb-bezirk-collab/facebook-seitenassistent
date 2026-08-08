from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

from app.media_monitor.fetchers.generic import fetch_homepage_source

SOURCE_NAME = 'NÖN'
DEFAULT_URL = 'https://www.noen.at/'


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix('www.')
    if host != 'noen.at':
        return False
    path = parsed.path.rstrip('/')
    if not path or path in {'/niederoesterreich', '/politik', '/wirtschaft', '/sport'}:
        return False
    # NÖN nutzt sprechende Pfade; Ressortübersichten werden ausgeschlossen.
    return len([part for part in path.split('/') if part]) >= 2 and bool(re.search(r'[a-zA-ZäöüÄÖÜß]', path))


def fetch_noen(limit: int = 40) -> list[dict[str, Any]]:
    source_url = os.getenv('NOEN_MONITOR_URL', DEFAULT_URL).strip() or DEFAULT_URL
    return fetch_homepage_source(
        source_name=SOURCE_NAME,
        source_url=source_url,
        base_url='https://www.noen.at/',
        article_url_predicate=_is_article_url,
        limit=limit,
    )
