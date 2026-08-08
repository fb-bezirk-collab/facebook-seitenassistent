from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo


LOCAL_TIMEZONE = ZoneInfo("Europe/Vienna")


class _ArticleMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.time_values: list[str] = []
        self.jsonld_blocks: list[str] = []
        self._in_jsonld = False
        self._json_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}
        tag = tag.lower()
        if tag == "meta":
            key = (attributes.get("property") or attributes.get("name") or attributes.get("itemprop") or "").strip().lower()
            content = attributes.get("content", "").strip()
            if key and content and key not in self.meta:
                self.meta[key] = content
        elif tag == "time":
            value = attributes.get("datetime", "").strip()
            if value:
                self.time_values.append(value)
        elif tag == "script" and "ld+json" in attributes.get("type", "").lower():
            self._in_jsonld = True
            self._json_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._json_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_jsonld:
            self.jsonld_blocks.append("".join(self._json_parts).strip())
            self._in_jsonld = False
            self._json_parts = []


def _parse_local_visible_datetime(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    # Österreichische Medien zeigen Datums-/Zeitangaben typischerweise in Europe/Vienna an.
    match = re.search(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})\s*[,|–-]?\s*(\d{1,2}):(\d{2})(?!\d)", text)
    if not match:
        return None
    day, month, year, hour, minute = map(int, match.groups())
    try:
        parsed = datetime(year, month, day, hour, minute, tzinfo=LOCAL_TIMEZONE)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).isoformat()


def extract_article_published_at(html_text: str) -> str | None:
    """Extrahiert das Veröffentlichungsdatum robust aus einer Artikelseite.

    Bevorzugt JSON-LD und standardisierte Meta-Tags. Als letzter Fallback
    wird eine sichtbare österreichische Datums-/Zeitangabe ausgewertet.
    """
    parser = _ArticleMetaParser()
    parser.feed(html_text or "")

    # JSON-LD hat die höchste Priorität.
    for block in parser.jsonld_blocks:
        try:
            parsed = json.loads(block)
        except (json.JSONDecodeError, TypeError):
            continue
        for article in iter_jsonld_articles(parsed):
            published = parse_published(str(article.get("datePublished") or ""))
            if published:
                return published

    # Übliche OpenGraph-/Article-/Schema-Metadaten.
    for key in (
        "article:published_time",
        "og:published_time",
        "datepublished",
        "date",
        "publishdate",
        "publication_date",
        "parsely-pub-date",
    ):
        published = parse_published(parser.meta.get(key))
        if published:
            return published

    for value in parser.time_values:
        published = parse_published(value) or _parse_local_visible_datetime(value)
        if published:
            return published

    # Letzter Fallback: sichtbare Angabe wie „08.08.2026, 07:11“.
    return _parse_local_visible_datetime(html_text)


ARTICLE_TYPES = {"article", "newsarticle", "reportagenewsarticle", "analysisnewsarticle", "blogposting"}


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def parse_published(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def category_from_url(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if not parts:
        return ""
    skip = {"s", "a", "news", "artikel", "article"}
    for part in parts[:-1]:
        normalized = clean_text(part.replace("-", " "))
        if normalized.lower() not in skip and not normalized.isdigit():
            return normalized.title()
    return ""


def _image_url(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for entry in value:
            candidate = _image_url(entry)
            if candidate:
                return candidate
    if isinstance(value, dict):
        for key in ("url", "contentUrl"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return ""


def _url_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("url", "@id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return ""


def _types(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.lower()}
    if isinstance(value, list):
        return {str(entry).lower() for entry in value}
    return set()


def iter_jsonld_articles(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for entry in value:
            yield from iter_jsonld_articles(entry)
        return
    if not isinstance(value, dict):
        return

    types = _types(value.get("@type"))
    if types & ARTICLE_TYPES:
        yield value

    for key, child in value.items():
        if key in {"publisher", "author", "creator"}:
            continue
        if isinstance(child, (dict, list)):
            yield from iter_jsonld_articles(child)


class _HomepageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.jsonld_blocks: list[str] = []
        self._href = ""
        self._anchor_parts: list[str] = []
        self._in_jsonld = False
        self._json_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}
        if tag.lower() == "a":
            self._href = attributes.get("href", "").strip()
            self._anchor_parts = []
        elif tag.lower() == "script" and "ld+json" in attributes.get("type", "").lower():
            self._in_jsonld = True
            self._json_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._json_parts.append(data)
        if self._href:
            self._anchor_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            text = clean_text(" ".join(self._anchor_parts))
            self.links.append((self._href, text))
            self._href = ""
            self._anchor_parts = []
        elif tag.lower() == "script" and self._in_jsonld:
            self.jsonld_blocks.append("".join(self._json_parts).strip())
            self._in_jsonld = False
            self._json_parts = []


def parse_homepage_articles(
    html_text: str,
    *,
    source_name: str,
    base_url: str,
    article_url_predicate,
    limit: int = 40,
) -> list[dict[str, Any]]:
    parser = _HomepageParser()
    parser.feed(html_text)

    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_item(title: str, url: str, teaser: str = "", published_at: str | None = None, image_url: str = "") -> None:
        if len(results) >= limit:
            return
        title = clean_text(title)
        absolute = urljoin(base_url, (url or "").strip())
        if not title or len(title) < 18 or not absolute or not article_url_predicate(absolute):
            return
        canonical = absolute.split("#", 1)[0]
        if canonical in seen:
            return
        seen.add(canonical)
        results.append({
            "source": source_name,
            "title": title,
            "teaser": clean_text(teaser),
            "url": canonical,
            "image_url": urljoin(base_url, image_url) if image_url else "",
            "published_at": published_at,
            "source_category": category_from_url(canonical),
        })

    # JSON-LD ist die bevorzugte Quelle, weil dort häufig Datum, Kurztext und Bild enthalten sind.
    for block in parser.jsonld_blocks:
        if len(results) >= limit:
            break
        try:
            parsed = json.loads(block)
        except (json.JSONDecodeError, TypeError):
            continue
        for article in iter_jsonld_articles(parsed):
            url = _url_value(article.get("url")) or _url_value(article.get("mainEntityOfPage"))
            title = str(article.get("headline") or article.get("name") or "")
            add_item(
                title,
                url,
                str(article.get("description") or ""),
                parse_published(str(article.get("datePublished") or article.get("dateModified") or "")),
                _image_url(article.get("image")),
            )
            if len(results) >= limit:
                break

    # Fallback für Startseiten, deren strukturierte Daten nur die Seite selbst beschreiben.
    for href, text in parser.links:
        if len(results) >= limit:
            break
        if len(text) < 25 or len(text) > 220:
            continue
        add_item(text, href)

    return results
