from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR


MEDIA_MONITOR_FILE = DATA_DIR / "media_monitor.json"


def _editorial_defaults() -> dict[str, Any]:
    """Struktur für den Redaktionsassistenten ab Version 2.5.1.

    Die Felder werden bereits angelegt, obwohl die KI sie erst im nächsten
    Entwicklungsschritt befüllt. Dadurch bleiben bestehende Meldungen und
    künftige Analysen kompatibel.
    """
    return {
        "political_brisanz": None,
        "communication_potential": None,
        "priority": "",
        "priority_reason": "",
        "political_angle": "",
        "communication_angles": [],
        "affected_groups": [],
        "headlines": {
            "sachlich": "",
            "pointiert": "",
            "emotional": "",
            "kurz": "",
        },
        "facebook_variants": {
            "sachlich": "",
            "pointiert": "",
            "emotional": "",
            "mobil": "",
        },
        "graphic": {
            "type": "",
            "idea": "",
            "reason": "",
        },
        "facts_confirmed": [],
        "facts_check": [],
        "hashtags": [],
    }


def _ensure_editorial_structure(item: dict[str, Any]) -> dict[str, Any]:
    defaults = _editorial_defaults()
    current = item.get("editorial")
    if not isinstance(current, dict):
        current = {}

    merged = defaults.copy()
    merged.update(current)

    for key in ("headlines", "facebook_variants", "graphic"):
        nested_default = defaults[key]
        nested_current = current.get(key)
        nested = nested_default.copy()
        if isinstance(nested_current, dict):
            nested.update(nested_current)
        merged[key] = nested

    for key in ("communication_angles", "affected_groups", "facts_confirmed", "facts_check", "hashtags"):
        if not isinstance(merged.get(key), list):
            merged[key] = []

    item["editorial"] = merged
    return item


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(source: str, url: str, title: str) -> str:
    normalized = "|".join(part.strip().lower() for part in (source, url.split("?", 1)[0], title))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_items() -> list[dict[str, Any]]:
    if not MEDIA_MONITOR_FILE.exists():
        return []
    try:
        content = json.loads(MEDIA_MONITOR_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(content, list):
        return []
    return [_ensure_editorial_structure(item) for item in content if isinstance(item, dict)]


def save_items(items: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary_file = Path(str(MEDIA_MONITOR_FILE) + ".tmp")
    temporary_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_file.replace(MEDIA_MONITOR_FILE)


def merge_fetched_items(fetched_items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    existing = load_items()
    known = {item.get("fingerprint") for item in existing if isinstance(item, dict) and item.get("fingerprint")}
    fetched_at = _now_iso()
    new_count = 0

    by_fingerprint = {
        item.get("fingerprint"): item
        for item in existing
        if isinstance(item, dict) and item.get("fingerprint")
    }

    for raw_item in fetched_items:
        fingerprint = _fingerprint(str(raw_item.get("source", "")), str(raw_item.get("url", "")), str(raw_item.get("title", "")))
        if fingerprint in known:
            # Bereits gespeicherte Artikel nachträglich mit einer inzwischen
            # ermittelten Veröffentlichungszeit ergänzen.
            existing_item = by_fingerprint.get(fingerprint)
            if existing_item and not existing_item.get("published_at") and raw_item.get("published_at"):
                existing_item["published_at"] = raw_item.get("published_at")
            continue
        item = {
            "id": fingerprint[:16], "fingerprint": fingerprint,
            "source": str(raw_item.get("source", "")), "title": str(raw_item.get("title", "")),
            "teaser": str(raw_item.get("teaser", "")), "url": str(raw_item.get("url", "")),
            "image_url": str(raw_item.get("image_url", "")), "published_at": raw_item.get("published_at"),
            "fetched_at": fetched_at, "source_category": str(raw_item.get("source_category", "")),
            "prefilter_status": "pending", "prefilter_reason": "",
            "category": "Noch nicht bewertet", "categories": [], "region": "–",
            "ai_summary": "", "ai_reason": "Noch nicht bewertet.",
            "score_political": None, "score_people": None, "score_profile": None,
            "score_social": None, "score_interest": None, "score_reliable": None,
            "score_total": None, "visibility": "pending", "status": "new",
            "notes": "", "created_post": False,
            "analysis_status": "", "analysis_error": "", "analysis_updated_at": None,
            "analysis_content_mode": "", "analysis_article_chars": 0, "analysis": {},
            "editorial": _editorial_defaults(),
        }
        existing.append(item)
        known.add(fingerprint)
        by_fingerprint[fingerprint] = item
        new_count += 1

    existing.sort(key=lambda item: item.get("published_at") or item.get("fetched_at") or "", reverse=True)
    save_items(existing)
    return existing, new_count
