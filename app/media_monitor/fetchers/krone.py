from __future__ import annotations

import html
import os
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from app.media_monitor.fetchers.common import extract_article_published_at, parse_homepage_articles
from app.media_monitor.fetchers.generic import HEADERS as GENERIC_HEADERS, response_text


SOURCE_NAME = "Krone"
DEFAULT_RSS_URL = "https://api.krone.at/v1/rss/rssfeed-google.xml?id=2311992"
DEFAULT_HOMEPAGE_URL = "https://www.krone.at/"
DEFAULT_POLITICS_URL = "https://www.krone.at/politik"
DEFAULT_POLITICS_ARCHIVE_URL = "https://www.krone.at/politik/archiv/2"
DEFAULT_INTERIOR_URL = "https://www.krone.at/innenpolitik"
DEFAULT_INTERIOR_ARCHIVE_URL = "https://www.krone.at/innenpolitik/archiv/2"
KRONE_DEBUG_TARGET = os.getenv("KRONE_DEBUG_TARGET", "4259228").strip()

def _debug_target_in_items(items: list[dict[str, Any]], target: str = KRONE_DEBUG_TARGET) -> bool:
    if not target:
        return False
    return any(target in str(item.get("url") or "") for item in items)

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


def _fetch_listing_items(url: str, limit: int) -> list[dict[str, Any]]:
    """Liest eine Krone-Übersichts-/Archivseite und extrahiert echte Artikel-URLs."""
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers=GENERIC_HEADERS,
    )
    response.raise_for_status()
    html_text = response_text(response)
    if not html_text.strip():
        raise RuntimeError(f"Krone-Seite hat keine Daten geliefert: {url}")

    items = parse_homepage_articles(
        html_text,
        source_name=SOURCE_NAME,
        base_url="https://www.krone.at/",
        article_url_predicate=_is_krone_article_url,
        limit=max(1, min(limit, 120)),
    )
    if not items:
        raise RuntimeError(f"Auf der Krone-Seite wurden keine Artikel gefunden: {url}")
    return items


def _extract_meta(html_text: str, prop: str) -> str:
    patterns = (
        rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}["\']',
        rf'<meta[^>]+name=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(prop)}["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.I)
        if match:
            return _clean_text(match.group(1))
    return ""


def _enrich_article(item: dict[str, Any]) -> dict[str, Any]:
    """Holt für einen entdeckten Krone-Artikel Datum/Zeit und öffentliche Metadaten."""
    enriched = dict(item)
    url = str(enriched.get("url") or "").strip()
    if not url:
        return enriched
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers=GENERIC_HEADERS)
        response.raise_for_status()
        html_text = response_text(response)

        published = extract_article_published_at(html_text)
        if published:
            enriched["published_at"] = published

        title = _extract_meta(html_text, "og:title")
        description = _extract_meta(html_text, "og:description")
        image = _extract_meta(html_text, "og:image")
        if title:
            enriched["title"] = title
        if description:
            enriched["teaser"] = description
        if image:
            enriched["image_url"] = image

        # Krone führt das Ressort auf der Artikelseite; JSON-LD/Meta bleibt
        # je nach Seitentyp unterschiedlich. Der bestehende Listing-Wert bleibt
        # deshalb als Fallback erhalten.
    except Exception as exc:
        print(f"Krone-Artikeldetails konnten nicht gelesen werden ({url}): {exc}", flush=True)
    return enriched


def _published_sort_value(item: dict[str, Any]) -> datetime:
    raw = str(item.get("published_at") or "").strip()
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def fetch_krone(limit: int = 40) -> list[dict[str, Any]]:
    """Krone-Discovery mit eigenem Kontingent je politischem Einstiegspunkt."""
    wanted = max(1, min(limit, 100))
    per_channel = max(50, wanted)
    homepage_url = os.getenv("KRONE_HOMEPAGE_URL", DEFAULT_HOMEPAGE_URL).strip() or DEFAULT_HOMEPAGE_URL
    politics_url = os.getenv("KRONE_POLITICS_URL", DEFAULT_POLITICS_URL).strip() or DEFAULT_POLITICS_URL
    interior_url = os.getenv("KRONE_INTERIOR_URL", DEFAULT_INTERIOR_URL).strip() or DEFAULT_INTERIOR_URL
    specs = [
        ("Innenpolitik", interior_url, "page"),
        ("Innenpolitik-Archiv 2", os.getenv("KRONE_INTERIOR_ARCHIVE_URL", DEFAULT_INTERIOR_ARCHIVE_URL).strip() or DEFAULT_INTERIOR_ARCHIVE_URL, "page"),
        ("Innenpolitik-Archiv 3", "https://www.krone.at/innenpolitik/archiv/3", "page"),
        ("Politik", politics_url, "page"),
        ("Politik-Archiv 2", os.getenv("KRONE_POLITICS_ARCHIVE_URL", DEFAULT_POLITICS_ARCHIVE_URL).strip() or DEFAULT_POLITICS_ARCHIVE_URL, "page"),
        ("Politik-Archiv 3", "https://www.krone.at/politik/archiv/3", "page"),
        ("RSS", "", "rss"),
        ("Startseite", homepage_url, "page"),
    ]
    batches, errors = [], []
    for label, url, kind in specs:
        try:
            batch = _fetch_rss_items(per_channel) if kind == "rss" else _fetch_listing_items(url, per_channel)
            print(
                f"KRONE DEBUG | Kanal={label} | erkannt={len(batch)} | "
                f"Target {KRONE_DEBUG_TARGET} gefunden={_debug_target_in_items(batch)}",
                flush=True,
            )
            if batch:
                batches.append(batch[:per_channel])
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            print(f"Krone-{label}-Abruf fehlgeschlagen: {exc}", flush=True)

    by_url, ordered_urls = {}, []
    for batch in batches:
        for item in batch:
            url = str(item.get("url") or "").split("#", 1)[0].rstrip("/").strip()
            if not url: continue
            if url not in by_url:
                copy=dict(item); copy["url"]=url; by_url[url]=copy; ordered_urls.append(url)
            else:
                for key in ("title","teaser","image_url","published_at","source_category"):
                    if not by_url[url].get(key) and item.get(key): by_url[url][key]=item[key]
    print(
        f"KRONE DEBUG | nach Deduplizierung={len(ordered_urls)} | "
        f"Target {KRONE_DEBUG_TARGET} vorhanden={any(KRONE_DEBUG_TARGET in url for url in ordered_urls)}",
        flush=True,
    )
    if not ordered_urls:
        raise RuntimeError("Krone konnte nicht gelesen werden: " + ("; ".join(errors) or "keine Meldungen gefunden"))

    candidate_urls=ordered_urls[:240]
    print(
        f"KRONE DEBUG | Detailkandidaten={len(candidate_urls)} | "
        f"Target {KRONE_DEBUG_TARGET} in Kandidaten={any(KRONE_DEBUG_TARGET in url for url in candidate_urls)}",
        flush=True,
    )
    enriched_by_url={}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures={pool.submit(_enrich_article,by_url[url]):url for url in candidate_urls}
        for future in as_completed(futures):
            url=futures[future]
            try: enriched_by_url[url]=future.result()
            except Exception: enriched_by_url[url]=by_url[url]
    merged=[enriched_by_url.get(url,by_url[url]) for url in candidate_urls]
    print(
        f"KRONE DEBUG | nach Detailabruf={len(merged)} | "
        f"Target {KRONE_DEBUG_TARGET} vorhanden={_debug_target_in_items(merged)}",
        flush=True,
    )
    merged.sort(key=_published_sort_value,reverse=True)
    final_items=merged[:wanted]
    target_rank = next(
        (idx + 1 for idx, item in enumerate(merged) if KRONE_DEBUG_TARGET in str(item.get("url") or "")),
        None,
    )
    print(
        f"KRONE DEBUG | final={len(final_items)} (Limit={wanted}) | "
        f"Target {KRONE_DEBUG_TARGET} Rang={target_rank or 'nicht vorhanden'} | "
        f"in final={_debug_target_in_items(final_items)}",
        flush=True,
    )
    return final_items
