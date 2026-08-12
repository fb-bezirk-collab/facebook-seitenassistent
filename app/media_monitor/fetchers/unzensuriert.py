from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

from app.media_monitor.fetchers.generic import fetch_homepage_source

SOURCE_NAME = 'Unzensuriert'
DEFAULT_URL = 'https://unzensuriert.at/'


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix('www.')
    if host != 'unzensuriert.at':
        return False
    path = parsed.path.strip('/')
    # Artikelseiten beginnen bei Unzensuriert mit einer numerischen Artikel-ID.
    return bool(re.match(r'^\d{4,}-[a-zA-Z0-9äöüÄÖÜß-]+/?$', path))


def fetch_unzensuriert(limit: int = 40) -> list[dict[str, Any]]:
    source_url = os.getenv('UNZENSURIERT_MONITOR_URL', DEFAULT_URL).strip() or DEFAULT_URL
    return fetch_homepage_source(
        source_name=SOURCE_NAME,
        source_url=source_url,
        base_url='https://unzensuriert.at/',
        article_url_predicate=_is_article_url,
        limit=limit,
    )
