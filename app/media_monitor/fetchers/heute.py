from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import requests

from app.media_monitor.fetchers.common import extract_article_published_at, parse_homepage_articles


SOURCE_NAME = "Heute"
DEFAULT_URL = "https://www.heute.at/"
DEFAULT_NOE_URL = "https://www.heute.at/a/niederoesterreich-heute-100289296"
REQUEST_TIMEOUT_SECONDS = 25
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Facebook-Seitenassistent/2.1"
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "de-AT,de;q=0.9,en;q=0.5"}


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host != "heute.at":
        return False
    path = parsed.path.rstrip("/")
    return path.startswith("/s/") and len(path.split("/")) >= 3


def _enrich_published_dates(items: list[dict[str, Any]], session: requests.Session) -> None:
    """Holt nur dann die Artikelseite, wenn auf der Startseite kein Datum vorhanden war."""
    for item in items:
        if item.get("published_at") or not item.get("url"):
            continue
        try:
            response = session.get(str(item["url"]), timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS)
            response.raise_for_status()
            published_at = extract_article_published_at(response.text)
            if published_at:
                item["published_at"] = published_at
        except requests.RequestException as exc:
            # Ein einzelner Artikel darf den gesamten Heute-Abruf nicht blockieren.
            print(f"Heute: Veröffentlichungszeit konnte für {item.get('url')} nicht gelesen werden: {exc}", flush=True)


def _fetch_listing(source_url: str, limit: int, session: requests.Session) -> list[dict[str, Any]]:
    response = session.get(source_url, timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS)
    response.raise_for_status()
    if not response.text.strip():
        raise RuntimeError(f"Heute.at hat unter {source_url} keine Daten geliefert.")
    items = parse_homepage_articles(
        response.text,
        source_name=SOURCE_NAME,
        base_url="https://www.heute.at/",
        article_url_predicate=_is_article_url,
        limit=max(1, min(limit, 100)),
    )
    _enrich_published_dates(items, session)
    return items


def fetch_heute(limit: int = 40) -> list[dict[str, Any]]:
    """Liest Heute über Startseite UND die eigene Niederösterreich-Seite.

    Für diese App ist Niederösterreich ein Kerngebiet. Relevante NÖ-Artikel dürfen
    daher nicht davon abhängen, ob sie gerade auf der bundesweiten Startseite stehen.
    """
    wanted = max(1, min(limit, 100))
    start_url = os.getenv("HEUTE_MONITOR_URL", DEFAULT_URL).strip() or DEFAULT_URL
    noe_url = os.getenv("HEUTE_NOE_MONITOR_URL", DEFAULT_NOE_URL).strip() or DEFAULT_NOE_URL

    by_url: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    with requests.Session() as session:
        for label, source_url in (("Niederösterreich", noe_url), ("Startseite", start_url)):
            try:
                items = _fetch_listing(source_url, max(60, wanted), session)
            except Exception as exc:
                errors.append(f"{label}: {exc}")
                print(f"Heute – {label} fehlgeschlagen: {exc}", flush=True)
                continue

            for item in items:
                url = str(item.get("url") or "").split("#", 1)[0].rstrip("/").strip()
                if not url:
                    continue
                if url not in by_url:
                    copy = dict(item)
                    copy["url"] = url
                    if label == "Niederösterreich" and not copy.get("source_category"):
                        copy["source_category"] = "Niederösterreich"
                    by_url[url] = copy
                else:
                    for key in ("title", "teaser", "image_url", "published_at", "source_category"):
                        if not by_url[url].get(key) and item.get(key):
                            by_url[url][key] = item[key]

    if not by_url:
        raise RuntimeError("Heute.at konnte nicht gelesen werden: " + ("; ".join(errors) or "keine Artikel gefunden"))

    # Neue Artikel zuerst. Fehlende Zeiten bleiben hinten.
    def sort_value(item: dict[str, Any]) -> str:
        return str(item.get("published_at") or "")

    merged = list(by_url.values())
    merged.sort(key=sort_value, reverse=True)
    return merged[:wanted]
