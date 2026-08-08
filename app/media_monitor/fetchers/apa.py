from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from app.media_monitor.fetchers.generic import fetch_homepage_source

SOURCE_NAME = 'APA (öffentlich)'
DEFAULT_URL = 'https://apa.at/'


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix('www.')
    if host != 'apa.at':
        return False
    parts = [part for part in parsed.path.split('/') if part]
    return len(parts) >= 2 and parts[0].lower() == 'news'


def fetch_apa(limit: int = 40) -> list[dict[str, Any]]:
    """Liest ausschließlich die öffentlich sichtbaren APA-Top-News auf apa.at.

    Dies ist ausdrücklich kein Zugriff auf APA-Basisdienst, NewsDesk oder andere
    lizenzpflichtige Meldungsdienste.
    """
    source_url = os.getenv('APA_PUBLIC_URL', DEFAULT_URL).strip() or DEFAULT_URL
    return fetch_homepage_source(
        source_name=SOURCE_NAME,
        source_url=source_url,
        base_url='https://apa.at/',
        article_url_predicate=_is_article_url,
        limit=limit,
    )
