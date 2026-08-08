from __future__ import annotations

import os
from typing import Any

import requests

from app.media_monitor.fetchers.rss import parse_feed

SOURCE_NAME = 'Kleine Zeitung'
DEFAULT_FEEDS = (
    'https://www.kleinezeitung.at/rss/politik',
    'https://www.kleinezeitung.at/rss/oesterreich',
    'https://www.kleinezeitung.at/rss/wirtschaft',
)
REQUEST_TIMEOUT_SECONDS = 25
HEADERS = {'User-Agent': 'Facebook-Seitenassistent/2.2', 'Accept-Language': 'de-AT,de;q=0.9'}


def fetch_kleine(limit: int = 40) -> list[dict[str, Any]]:
    configured = os.getenv('KLEINE_RSS_URLS', '').strip()
    feeds = tuple(part.strip() for part in configured.split(',') if part.strip()) if configured else DEFAULT_FEEDS
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    errors: list[str] = []
    per_feed = max(15, limit)
    for url in feeds:
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS)
            response.raise_for_status()
            for item in parse_feed(response.text, source_name=SOURCE_NAME, base_url='https://www.kleinezeitung.at/', limit=per_feed):
                if item['url'] in seen:
                    continue
                seen.add(item['url'])
                combined.append(item)
        except Exception as exc:
            errors.append(f'{url}: {exc}')
    combined.sort(key=lambda item: item.get('published_at') or '', reverse=True)
    if not combined:
        raise RuntimeError('Die RSS-Feeds der Kleinen Zeitung konnten nicht gelesen werden.' + (f' {errors[0]}' if errors else ''))
    return combined[:limit]
