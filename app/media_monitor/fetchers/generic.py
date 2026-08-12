from __future__ import annotations

import re
from typing import Any, Callable

import requests

from app.media_monitor.fetchers.common import extract_article_published_at, parse_homepage_articles

REQUEST_TIMEOUT_SECONDS = 30
REQUEST_ATTEMPTS = 2
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Facebook-Seitenassistent/3.0'
HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept-Language': 'de-AT,de;q=0.9,en;q=0.5',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}


def _get_with_retry(session: requests.Session, url: str) -> requests.Response:
    last_error: requests.RequestException | None = None
    for attempt in range(REQUEST_ATTEMPTS):
        try:
            return session.get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt + 1 >= REQUEST_ATTEMPTS:
                raise
    if last_error is not None:
        raise last_error
    raise RuntimeError(f'Abruf fehlgeschlagen: {url}')


def response_text(response: requests.Response) -> str:
    """Dekodiert HTML robust und bevorzugt echtes UTF-8.

    requests setzt bei ``text/html`` ohne Charset historisch oft ISO-8859-1.
    Viele österreichische Seiten liefern in diesem Fall trotzdem UTF-8. Das
    führte zu Texten wie ``fÃ¼r``. Hier wird zuerst ein im HTML deklarierter
    Charset berücksichtigt; ist der Byte-Inhalt gültiges UTF-8, hat UTF-8
    Vorrang vor einem bloßen ISO-8859-1-Default.
    """
    raw = response.content or b''
    if not raw:
        return ''

    # BOM ist eindeutig.
    if raw.startswith(b'\xef\xbb\xbf'):
        return raw.decode('utf-8-sig', errors='replace')

    head = raw[:8192].decode('ascii', errors='ignore')
    match = re.search(
        r'<meta[^>]+charset\s*=\s*["\']?\s*([a-zA-Z0-9._-]+)',
        head,
        flags=re.I,
    )
    if not match:
        match = re.search(
            r'<meta[^>]+content\s*=\s*["\'][^"\']*charset\s*=\s*([a-zA-Z0-9._-]+)',
            head,
            flags=re.I,
        )
    declared = (match.group(1) if match else '').strip().lower()

    # Gültiges UTF-8 ist bei modernen News-Seiten die verlässlichste Wahl.
    try:
        utf8 = raw.decode('utf-8')
        if declared in {'', 'utf-8', 'utf8', 'iso-8859-1', 'latin-1', 'latin1'}:
            return utf8
    except UnicodeDecodeError:
        pass

    for encoding in (declared, response.encoding or '', response.apparent_encoding or '', 'cp1252', 'latin1'):
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue

    return raw.decode('utf-8', errors='replace')


def enrich_published_dates(items: list[dict[str, Any]], session: requests.Session, source_name: str) -> None:
    for item in items:
        if item.get('published_at') or not item.get('url'):
            continue
        try:
            response = _get_with_retry(session, str(item['url']))
            response.raise_for_status()
            published_at = extract_article_published_at(response_text(response))
            if published_at:
                item['published_at'] = published_at
        except requests.RequestException as exc:
            print(f'{source_name}: Veröffentlichungszeit konnte für {item.get("url")} nicht gelesen werden: {exc}', flush=True)


def fetch_homepage_source(
    *,
    source_name: str,
    source_url: str,
    base_url: str,
    article_url_predicate: Callable[[str], bool],
    limit: int = 40,
    enrich_dates: bool = True,
) -> list[dict[str, Any]]:
    with requests.Session() as session:
        response = _get_with_retry(session, source_url)
        response.raise_for_status()
        html_text = response_text(response)
        if not html_text.strip():
            raise RuntimeError(f'{source_name} hat keine Daten geliefert.')
        items = parse_homepage_articles(
            html_text,
            source_name=source_name,
            base_url=base_url,
            article_url_predicate=article_url_predicate,
            limit=max(1, min(limit, 100)),
        )
        if not items:
            raise RuntimeError(f'Bei {source_name} wurden keine aktuellen Artikel gefunden.')
        if enrich_dates:
            enrich_published_dates(items, session, source_name)
        return items
