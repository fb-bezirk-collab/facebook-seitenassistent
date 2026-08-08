from __future__ import annotations

from typing import Any, Callable

import requests

from app.media_monitor.fetchers.common import extract_article_published_at, parse_homepage_articles

REQUEST_TIMEOUT_SECONDS = 25
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Facebook-Seitenassistent/2.2'
HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept-Language': 'de-AT,de;q=0.9,en;q=0.5',
}


def enrich_published_dates(items: list[dict[str, Any]], session: requests.Session, source_name: str) -> None:
    for item in items:
        if item.get('published_at') or not item.get('url'):
            continue
        try:
            response = session.get(str(item['url']), timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS)
            response.raise_for_status()
            published_at = extract_article_published_at(response.text)
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
        response = session.get(source_url, timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS)
        response.raise_for_status()
        if not response.text.strip():
            raise RuntimeError(f'{source_name} hat keine Daten geliefert.')
        items = parse_homepage_articles(
            response.text,
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
