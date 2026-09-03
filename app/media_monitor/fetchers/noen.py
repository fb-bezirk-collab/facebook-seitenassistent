from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.media_monitor.fetchers.generic import fetch_homepage_source

SOURCE_NAME = "NÖN"
DEFAULT_URL = "https://www.noen.at/"
DEFAULT_NOE_POLITICS_URL = "https://www.noen.at/niederoesterreich/politik"
DEFAULT_GAENSERNDORF_URL = "https://www.noen.at/gaenserndorf"


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host != "noen.at":
        return False
    path = parsed.path.rstrip("/")
    if not path or path in {
        "/niederoesterreich", "/niederoesterreich/politik",
        "/politik", "/wirtschaft", "/sport", "/gaenserndorf",
    }:
        return False
    return len([part for part in path.split("/") if part]) >= 2 and bool(
        re.search(r"[a-zA-ZäöüÄÖÜß]", path)
    )


def _sort_value(item: dict[str, Any]) -> datetime:
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


def fetch_noen(limit: int = 40) -> list[dict[str, Any]]:
    """NÖN wird über mehrere für diese App relevante Einstiege entdeckt.

    Priorität der Discovery:
    1. Bezirk Gänserndorf
    2. Niederösterreich/Politik
    3. NÖN-Startseite
    """
    wanted = max(1, min(limit, 100))
    per_channel = max(50, wanted)

    specs = [
        (
            "Gänserndorf",
            os.getenv("NOEN_GAENSERNDORF_URL", DEFAULT_GAENSERNDORF_URL).strip()
            or DEFAULT_GAENSERNDORF_URL,
        ),
        (
            "Niederösterreich Politik",
            os.getenv("NOEN_NOE_POLITICS_URL", DEFAULT_NOE_POLITICS_URL).strip()
            or DEFAULT_NOE_POLITICS_URL,
        ),
        (
            "Startseite",
            os.getenv("NOEN_MONITOR_URL", DEFAULT_URL).strip() or DEFAULT_URL,
        ),
    ]

    by_url: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for label, source_url in specs:
        try:
            items = fetch_homepage_source(
                source_name=SOURCE_NAME,
                source_url=source_url,
                base_url="https://www.noen.at/",
                article_url_predicate=_is_article_url,
                limit=per_channel,
                enrich_dates=True,
            )
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            print(f"NÖN – {label} fehlgeschlagen: {exc}", flush=True)
            continue

        for item in items:
            url = str(item.get("url") or "").split("#", 1)[0].rstrip("/").strip()
            if not url:
                continue
            if url not in by_url:
                copy = dict(item)
                copy["url"] = url
                if label == "Gänserndorf":
                    copy["source_category"] = copy.get("source_category") or "Bezirk Gänserndorf"
                elif label == "Niederösterreich Politik":
                    copy["source_category"] = copy.get("source_category") or "Niederösterreich Politik"
                by_url[url] = copy
            else:
                for key in ("title", "teaser", "image_url", "published_at", "source_category"):
                    if not by_url[url].get(key) and item.get(key):
                        by_url[url][key] = item[key]

    if not by_url:
        raise RuntimeError(
            "NÖN konnte über Gänserndorf, NÖ-Politik und Startseite nicht gelesen werden: "
            + ("; ".join(errors) or "keine Artikel gefunden")
        )

    merged = list(by_url.values())
    merged.sort(key=_sort_value, reverse=True)
    return merged[:wanted]
