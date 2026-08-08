from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urljoin

from app.media_monitor.fetchers.common import clean_text, parse_published


def _first_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for child in element.iter():
        local_name = child.tag.rsplit('}', 1)[-1].lower()
        if local_name in names and child.text:
            value = child.text.strip()
            if value:
                return value
    return ''


def _extract_link(item: ET.Element) -> str:
    for child in item.iter():
        local_name = child.tag.rsplit('}', 1)[-1].lower()
        if local_name == 'link':
            href = (child.attrib.get('href') or child.attrib.get('resource') or '').strip()
            if href:
                return href
            if child.text and child.text.strip():
                return child.text.strip()
    # RSS 1.0/RDF kann die URL auch direkt am Element führen.
    for key, value in item.attrib.items():
        if key.rsplit('}', 1)[-1].lower() in {'about', 'resource'} and value:
            return value.strip()
    return ''


def _extract_image(item: ET.Element, description: str) -> str:
    for child in item.iter():
        local_name = child.tag.rsplit('}', 1)[-1].lower()
        if local_name in {'content', 'thumbnail', 'enclosure'}:
            candidate = (child.attrib.get('url') or child.attrib.get('href') or child.attrib.get('resource') or '').strip()
            media_type = (child.attrib.get('type') or '').lower()
            if candidate and (
                local_name in {'thumbnail', 'content'}
                or media_type.startswith('image/')
                or re.search(r'\.(?:jpe?g|png|webp)(?:\?|$)', candidate, re.I)
            ):
                return candidate
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', description or '', flags=re.I)
    return html.unescape(match.group(1)).strip() if match else ''


def parse_feed(
    xml_text: str,
    *,
    source_name: str,
    base_url: str,
    limit: int = 40,
) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    entries = [
        node for node in root.iter()
        if node.tag.rsplit('}', 1)[-1].lower() in {'item', 'entry'}
    ]
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for item in entries:
        title = clean_text(_first_text(item, ('title',)))
        url = _extract_link(item)
        description_raw = _first_text(item, ('description', 'summary', 'content', 'encoded'))
        teaser = clean_text(description_raw)
        published_raw = _first_text(item, ('pubdate', 'published', 'updated', 'date', 'issued', 'created'))
        image_url = _extract_image(item, description_raw)
        category = clean_text(_first_text(item, ('category', 'subject')))

        if not title or not url:
            continue
        url = urljoin(base_url, url).split('#', 1)[0]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        results.append({
            'source': source_name,
            'title': title,
            'teaser': teaser,
            'url': url,
            'image_url': urljoin(base_url, image_url) if image_url else '',
            'published_at': parse_published(published_raw),
            'source_category': category,
        })
        if len(results) >= limit:
            break
    return results
