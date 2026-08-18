from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from app.config import DATA_DIR
from app.media_monitor.fetchers.common import clean_text, repair_mojibake


MEDIA_MONITOR_FILE = DATA_DIR / "media_monitor.json"



ARCHIVE_AFTER_DAYS = 7


def _parse_item_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _archive_reference_time(item: dict[str, Any]) -> datetime | None:
    """Veröffentlichungsdatum hat Vorrang; Fetched-at ist nur Fallback."""
    return _parse_item_datetime(item.get("published_at")) or _parse_item_datetime(item.get("fetched_at"))


def _has_analysis(item: dict[str, Any]) -> bool:
    if str(item.get("analysis_status") or "").lower() == "done":
        return True
    analysis = item.get("analysis")
    if isinstance(analysis, dict) and any(bool(v) for v in analysis.values()):
        return True
    editorial = item.get("editorial")
    if isinstance(editorial, dict):
        return bool(
            editorial.get("political_angle")
            or editorial.get("priority_reason")
            or editorial.get("facts_confirmed")
        )
    return False


def _was_used(item: dict[str, Any]) -> bool:
    return bool(
        item.get("created_post")
        or str(item.get("draft_id") or "").strip()
        or str(item.get("share_draft_id") or "").strip()
        or item.get("draft_created_at")
        or item.get("share_draft_created_at")
        or str(item.get("workflow_status") or "") in {"draft_created", "share_draft_created", "published"}
    )


def _apply_archive_metadata(item: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    reference = _archive_reference_time(item)
    should_archive = bool(reference and reference < now - timedelta(days=ARCHIVE_AFTER_DAYS))
    was_archived = bool(item.get("archived"))
    item["archived"] = should_archive
    item["archive_has_analysis"] = _has_analysis(item)
    item["archive_was_used"] = _was_used(item)
    if should_archive and not was_archived:
        item["archived_at"] = now.isoformat()
    elif not should_archive:
        item["archived_at"] = None
    return item


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


def _repair_saved_text(value: Any) -> Any:
    """Repariert auch bereits gespeicherte Mojibake-Texte rekursiv.

    Damit werden nicht nur neue Fetcher-Texte, sondern auch ältere Titel,
    KI-Kurzfassungen, Begründungen und Redaktionsfelder korrekt angezeigt.
    """
    if isinstance(value, str):
        return repair_mojibake(value)
    if isinstance(value, list):
        return [_repair_saved_text(item) for item in value]
    if isinstance(value, dict):
        return {key: _repair_saved_text(item) for key, item in value.items()}
    return value


def load_items() -> list[dict[str, Any]]:
    if not MEDIA_MONITOR_FILE.exists():
        return []
    try:
        content = json.loads(MEDIA_MONITOR_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(content, list):
        return []
    now = datetime.now(timezone.utc)
    repaired = [
        _apply_archive_metadata(_ensure_editorial_structure(_repair_saved_text(item)), now=now)
        for item in content if isinstance(item, dict)
    ]
    # Reparaturen und Archiv-Metadaten dauerhaft speichern, damit alte Werte nicht bei jedem
    # Seitenaufruf erneut aus dem Volume gelesen werden.
    if repaired != content:
        try:
            save_items(repaired)
        except OSError:
            pass
    return repaired


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
    by_source_url = {
        (str(item.get("source", "")).strip().lower(), str(item.get("url", "")).split("#", 1)[0].split("?", 1)[0]): item
        for item in existing
        if isinstance(item, dict) and item.get("url")
    }

    for raw_item in fetched_items:
        raw_source = clean_text(str(raw_item.get("source", "")))
        raw_url = str(raw_item.get("url", "")).strip()
        raw_title = clean_text(str(raw_item.get("title", "")))
        raw_teaser = clean_text(str(raw_item.get("teaser", "")))
        fingerprint = _fingerprint(raw_source, raw_url, raw_title)
        canonical_url = raw_url.split("#", 1)[0].split("?", 1)[0]
        existing_item = by_fingerprint.get(fingerprint) or by_source_url.get((raw_source.strip().lower(), canonical_url))
        if existing_item is not None:
            # Nicht nur das Datum nachtragen: 3.0.3 korrigiert damit auch
            # bereits gespeicherte Mojibake-Titel (z. B. fÃ¼r -> für), ohne
            # denselben Artikel wegen des geänderten Titels doppelt anzulegen.
            if raw_title and raw_title != str(existing_item.get("title", "")):
                existing_item["title"] = raw_title
            if raw_teaser and raw_teaser != existing_item.get("teaser"):
                existing_item["teaser"] = raw_teaser
            if raw_item.get("image_url") and not existing_item.get("image_url"):
                existing_item["image_url"] = raw_item.get("image_url")
            if raw_item.get("source_category"):
                existing_item["source_category"] = raw_item.get("source_category")
            if not existing_item.get("published_at") and raw_item.get("published_at"):
                existing_item["published_at"] = raw_item.get("published_at")
            continue
        item = {
            "id": fingerprint[:16], "fingerprint": fingerprint,
            "source": raw_source, "title": raw_title,
            "teaser": raw_teaser, "url": raw_url,
            "image_url": str(raw_item.get("image_url", "")), "published_at": raw_item.get("published_at"),
            "fetched_at": fetched_at, "source_category": str(raw_item.get("source_category", "")),
            "prefilter_status": "pending", "prefilter_reason": "",
            "category": "Noch nicht bewertet", "categories": [], "region": "–",
            "ai_summary": "", "ai_reason": "Noch nicht bewertet.",
            "score_political": None, "score_people": None, "score_profile": None,
            "score_social": None, "score_interest": None, "score_reliable": None,
            "score_total": None, "visibility": "pending", "status": "new",
            "notes": "", "created_post": False, "draft_id": "", "draft_created_at": None, "workflow_status": "analysis_pending",
            "analysis_status": "", "analysis_error": "", "analysis_updated_at": None,
            "analysis_content_mode": "", "analysis_article_chars": 0, "analysis": {},
            "archived": False, "archived_at": None, "archive_has_analysis": False, "archive_was_used": False,
            "editorial": _editorial_defaults(),
        }
        existing.append(item)
        known.add(fingerprint)
        by_fingerprint[fingerprint] = item
        new_count += 1

    existing.sort(key=lambda item: item.get("published_at") or item.get("fetched_at") or "", reverse=True)
    save_items(existing)
    return existing, new_count
