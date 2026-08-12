from __future__ import annotations

import html
import json
import os
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from app.media_monitor.fetchers.common import clean_text, extract_article_details, parse_homepage_articles
from app.media_monitor.fetchers.generic import _get_with_retry, response_text

SOURCE_NAME = 'NIUS Österreich'
# Absichtlich nur der Österreich-Tag. Der allgemeine NIUS-Newsfeed darf nicht verwendet werden.
DEFAULT_URL = 'https://nius.de/tag/oesterreich'
BASE_URL = 'https://nius.de/'

_ALLOWED_ROOTS = {
    'politik', 'gesellschaft', 'wirtschaft', 'kriminalitaet', 'energie',
    'analyse', 'kommentar', 'news', 'nachrichten', 'nius-live',
}
_EXCLUDED_ROOTS = {
    'tag', 'all-news', 'shows', 'clips', 'radio', 'autoren', 'abo',
    'shop', 'live-stream', 'nius-live', 'suche', 'search',
}


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix('www.')
    if host != 'nius.de':
        return False
    parts = [part for part in parsed.path.split('/') if part]
    if len(parts) < 2:
        return False
    if parts[0] == 'tag' or parts[0] in _EXCLUDED_ROOTS and len(parts) == 1:
        return False
    # NIUS verwendet mehrere Artikelpfade, z. B. /politik/<slug>,
    # /gesellschaft/news/<slug>/<uuid> oder /nachrichten/<slug>.
    return parts[0] in _ALLOWED_ROOTS and len(parts[-1]) >= 8


def _decode_embedded(value: str) -> str:
    text = html.unescape(value)
    text = text.replace('\\/', '/')
    # Next/React serialisiert Sonderzeichen häufig als \uXXXX.
    try:
        text = re.sub(
            r'\\u([0-9a-fA-F]{4})',
            lambda m: chr(int(m.group(1), 16)),
            text,
        )
    except (ValueError, OverflowError):
        pass
    return text


def _discover_embedded_article_urls(html_text: str, source_url: str) -> list[str]:
    """Findet NIUS-Artikelpfade auch in Next.js/RSC-Serialisierungen.

    Die Österreich-Tagseite rendert die Karten clientseitig. In der HTML-
    Antwort sind deren Pfade jedoch typischerweise in serialisierten React-
    Daten enthalten, auch wenn normale <a>-Links beim Parser fehlen.
    """
    decoded = _decode_embedded(html_text)
    candidates: list[str] = []

    patterns = (
        r'https?://(?:www\.)?nius\.de/[^"\'<>\\\s]+',
        r'(?<![A-Za-z0-9])/(?:politik|gesellschaft|wirtschaft|kriminalitaet|energie|analyse|kommentar|news|nachrichten|nius-live)/[^"\'<>\\\s]+',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, decoded, flags=re.I):
            raw = match.group(0).rstrip('),.;]}')
            url = urljoin(BASE_URL, raw).split('#', 1)[0]
            if _is_article_url(url) and url not in candidates:
                candidates.append(url)

    return candidates


def _extract_next_data_urls(html_text: str) -> list[str]:
    """Zusätzlicher Fallback für __NEXT_DATA__-JSON, falls vorhanden."""
    urls: list[str] = []
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html_text,
        flags=re.I | re.S,
    )
    if not match:
        return urls
    try:
        payload = json.loads(html.unescape(match.group(1)))
    except (json.JSONDecodeError, TypeError):
        return urls

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str):
            candidate = urljoin(BASE_URL, value)
            if _is_article_url(candidate) and candidate not in urls:
                urls.append(candidate)

    walk(payload)
    return urls


def fetch_nius_at(limit: int = 40) -> list[dict[str, Any]]:
    source_url = os.getenv('NIUS_AT_MONITOR_URL', DEFAULT_URL).strip() or DEFAULT_URL
    max_items = max(1, min(limit, 100))

    with requests.Session() as session:
        response = _get_with_retry(session, source_url)
        response.raise_for_status()
        page_html = response_text(response)
        if not page_html.strip():
            raise RuntimeError(f'{SOURCE_NAME} hat keine Daten geliefert.')

        # Falls NIUS wieder serverseitige Links/JSON-LD ausliefert, nutzen wir
        # zuerst den normalen Parser.
        items = parse_homepage_articles(
            page_html,
            source_name=SOURCE_NAME,
            base_url=BASE_URL,
            article_url_predicate=_is_article_url,
            limit=max_items,
        )
        if items:
            return items

        # Aktuell ist die Tagseite clientseitig gerendert. Artikelpfade werden
        # aus den eingebetteten Next/React-Daten gewonnen. Es wird ausdrücklich
        # NICHT auf die NIUS-Hauptseite oder /news ausgewichen.
        urls: list[str] = []
        for candidate in _extract_next_data_urls(page_html) + _discover_embedded_article_urls(page_html, source_url):
            if candidate not in urls:
                urls.append(candidate)
            if len(urls) >= max_items:
                break

        if not urls:
            raise RuntimeError(
                'Auf der NIUS-Österreich-Tagseite wurden keine Artikelpfade gefunden. '
                'Es wird bewusst nicht auf allgemeine NIUS-Meldungen ausgewichen.'
            )

        results: list[dict[str, Any]] = []
        for url in urls:
            try:
                article_response = _get_with_retry(session, url)
                article_response.raise_for_status()
                details = extract_article_details(
                    response_text(article_response),
                    source_name=SOURCE_NAME,
                    url=url,
                )
                if details.get('title') and len(str(details['title'])) >= 18:
                    results.append(details)
            except requests.RequestException as exc:
                print(f'{SOURCE_NAME}: Artikel konnte nicht gelesen werden: {url}: {exc}', flush=True)
            if len(results) >= max_items:
                break

        if not results:
            raise RuntimeError(
                'NIUS-Österreich-Artikelpfade wurden gefunden, aber keine Artikeldetails konnten gelesen werden.'
            )
        return results
