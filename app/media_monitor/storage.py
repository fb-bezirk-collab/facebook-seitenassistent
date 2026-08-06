from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR


MEDIA_MONITOR_FILE = DATA_DIR / "media_monitor.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(source: str, url: str, title: str) -> str:
    normalized = "|".join(
        part.strip().lower()
        for part in (source, url.split("?", 1)[0], title)
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_items() -> list[dict[str, Any]]:
    if not MEDIA_MONITOR_FILE.exists():
        return []

    try:
        content = json.loads(MEDIA_MONITOR_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    return content if isinstance(content, list) else []


def save_items(items: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary_file = Path(str(MEDIA_MONITOR_FILE) + ".tmp")
    temporary_file.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_file.replace(MEDIA_MONITOR_FILE)


def merge_fetched_items(fetched_items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    existing = load_items()
    known = {
        item.get("fingerprint")
        for item in existing
        if isinstance(item, dict) and item.get("fingerprint")
    }
    fetched_at = _now_iso()
    new_count = 0

    for raw_item in fetched_items:
        fingerprint = _fingerprint(
            str(raw_item.get("source", "")),
            str(raw_item.get("url", "")),
            str(raw_item.get("title", "")),
        )
        if fingerprint in known:
            continue

        item = {
            "id": fingerprint[:16],
            "fingerprint": fingerprint,
            "source": str(raw_item.get("source", "")),
            "title": str(raw_item.get("title", "")),
            "teaser": str(raw_item.get("teaser", "")),
            "url": str(raw_item.get("url", "")),
            "image_url": str(raw_item.get("image_url", "")),
            "published_at": raw_item.get("published_at"),
            "fetched_at": fetched_at,
            "source_category": str(raw_item.get("source_category", "")),
            "category": "Noch nicht bewertet",
            "region": "–",
            "ai_summary": "",
            "ai_reason": "KI-Bewertung folgt in einem späteren Schritt.",
            "score_total": None,
            "status": "new",
            "notes": "",
            "created_post": False,
        }
        existing.append(item)
        known.add(fingerprint)
        new_count += 1

    existing.sort(
        key=lambda item: item.get("published_at") or item.get("fetched_at") or "",
        reverse=True,
    )
    save_items(existing)
    return existing, new_count
