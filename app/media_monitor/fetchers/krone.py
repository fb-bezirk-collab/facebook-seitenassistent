from __future__ import annotations

import html
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from app.media_monitor.fetchers.generic import fetch_homepage_source


SOURCE_NAME = "Krone"
DEFAULT_RSS_URL = "https://api.krone.at/v1/rss/rssfeed-google.xml?id=2311992"
DEFAULT_HOMEPAGE_URL = "https://www.krone.at/"
DEFAULT_POLITICS_URL = "https://www.krone.at/politik"
REQUEST_TIMEOUT_SECONDS = 25
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "Facebook-Seitenassistent/2.0"
)


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _first_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for child in element.iter():
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name in names and child.text:
            value = child.text.strip()
            if value:
                return value
    return ""


def _extract_link(item: ET.Element) -> str:
    for child in item.iter():
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name == "link":
            href = (child.attrib.get("href") or "").strip()
            if href:
                return href
            if child.text and child.text.strip():
                return child.text.strip()
    return ""


def _extract_image(item: ET.Element, description: str) -> str:
    for child in item.iter():
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name in {"content", "thumbnail", "enclosure"}:
            candidate = (
                child.attrib.get("url")
                or child.attrib.get("href")
                or ""
            ).strip()
            media_type = (child.attrib.get("type") or "").lower()
            if candidate and (
                local_name in {"thumbnail", "content"}
                or media_type.startswith("image/")
                or re.search(r"\.(?:jpe?g|png|webp)(?:\?|$)", candidate, re.I)
            ):
                return candidate

    match = re.search(
        r"<img[^>]+src=[\"']([^\"']+)[\"']",
        description or "",
        flags=re.I,
    )
    return html.unescape(match.group(1)).strip() if match else ""


def _parse_published(value: str) -> str | None:
    value = value.strip()
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


def _parse_feed(xml_text: str, limit: int) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    entries = [
        node
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}
    ]

    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for item in entries:
        title = _clean_text(_first_text(item, ("title",)))
        url = _extract_link(item)
        description_raw = _first_text(
            item,
            ("description", "summary", "content", "encoded"),
        )
        teaser = _clean_text(description_raw)
        published_raw = _first_text(
            item,
            ("pubdate", "published", "updated", "date"),
        )
        image_url = _extract_image(item, description_raw)
        category = _clean_text(_first_text(item, ("category",)))

        if not title or not url:
            continue

        url = urljoin("https://www.krone.at/", url)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        results.append(
            {
                "source": SOURCE_NAME,
                "title": title,
                "teaser": teaser,
                "url": url,
                "image_url": image_url,
                "published_at": _parse_published(published_raw),
                "source_category": category,
            }
        )
        if len(results) >= limit:
            break

    return results


def _is_krone_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host != "krone.at":
        return False
    return bool(re.fullmatch(r"/\d{5,}", parsed.path.rstrip("/")))


def _fetch_rss_items(limit: int) -> list[dict[str, Any]]:
    rss_url = os.getenv("KRONE_RSS_URL", DEFAULT_RSS_URL).strip() or DEFAULT_RSS_URL
    response = requests.get(
        rss_url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
            "Accept-Language": "de-AT,de;q=0.9,en;q=0.5",
        },
    )
    response.raise_for_status()
    if not response.content.strip():
        raise RuntimeError("Der Krone-RSS-Feed hat keine Daten geliefert.")
    response.encoding = response.encoding or "utf-8"
    try:
        return _parse_feed(response.text, limit=max(1, min(limit, 100)))
    except ET.ParseError as exc:
        raise RuntimeError("Der Krone-RSS-Feed konnte nicht gelesen werden.") from exc


def _fetch_page_items(url: str, limit: int) -> list[dict[str, Any]]:
    return fetch_homepage_source(
        source_name=SOURCE_NAME,
        source_url=url,
        base_url="https://www.krone.at/",
        article_url_predicate=_is_krone_article_url,
        limit=max(1, min(limit, 100)),
        enrich_dates=False,
    )


def fetch_krone(limit: int = 40) -> list[dict[str, Any]]:
    """Entdeckt Krone-Meldungen über Politikseite, Startseite und RSS."""
    wanted = max(1, min(limit, 100))
    homepage_url = os.getenv("KRONE_HOMEPAGE_URL", DEFAULT_HOMEPAGE_URL).strip() or DEFAULT_HOMEPAGE_URL
    politics_url = os.getenv("KRONE_POLITICS_URL", DEFAULT_POLITICS_URL).strip() or DEFAULT_POLITICS_URL

    batches: list[list[dict[str, Any]]] = []
    errors: list[str] = []

    for label, loader in (
        ("Politik", lambda: _fetch_page_items(politics_url, wanted)),
        ("Startseite", lambda: _fetch_page_items(homepage_url, wanted)),
        ("RSS", lambda: _fetch_rss_items(wanted)),
    ):
        try:
            batch = loader()
            if batch:
                batches.append(batch)
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            print(f"Krone-{label}-Abruf fehlgeschlagen: {exc}", flush=True)

    merged: list[dict[str, Any]] = []
    by_url: dict[str, dict[str, Any]] = {}
    for batch in batches:
        for item in batch:
            url = str(item.get("url") or "").split("#", 1)[0].strip()
            if not url:
                continue
            existing = by_url.get(url)
            if existing is None:
                copy = dict(item)
                copy["url"] = url
                by_url[url] = copy
                merged.append(copy)
            else:
                for key in ("title", "teaser", "image_url", "published_at", "source_category"):
                    if not existing.get(key) and item.get(key):
                        existing[key] = item[key]

    if not merged:
        detail = "; ".join(errors) if errors else "keine Meldungen gefunden"
        raise RuntimeError(
            f"Krone konnte über Politikseite, Startseite und RSS nicht gelesen werden: {detail}"
        )
    return merged[:wanted]
