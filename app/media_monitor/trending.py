from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


API_URL = "https://api.openai.com/v1/responses"
TREND_WINDOW_HOURS = 24


class TrendingError(RuntimeError):
    pass


TREND_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "item_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["label", "item_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clusters"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """
Du erkennst medienübergreifend identische konkrete Nachrichtenereignisse in österreichischen Medien.
Gruppiere Artikel NUR dann, wenn sie über dasselbe konkrete Ereignis, dieselbe Entscheidung,
dieselbe neue Aussage, denselben Vorfall oder dieselbe unmittelbar zusammenhängende Entwicklung berichten.

Nicht gruppieren:
- bloß weil beide Artikel dasselbe Oberthema haben (z. B. Migration, EU, Teuerung),
- verschiedene Ereignisse zur selben Person,
- allgemeine Analysen mit einem aktuellen Einzelereignis,
- zeitlich oder sachlich voneinander unabhängige Geschichten.

Ein Cluster ist nur gültig, wenn mindestens zwei verschiedene Medienquellen vertreten sind.

WICHTIG: Überschriften müssen nicht ähnlich formuliert sein. Entscheidend ist das zugrunde liegende konkrete Nachrichtenereignis. Zwei Medien können dasselbe Ereignis mit völlig verschiedenen Headlines, Blickwinkeln oder Einzelaspekten beschreiben. Nutze Titel UND Summary/Teaser und erkenne gemeinsame Akteure, Zahlen, Entscheidungen, Forderungen und Vorgänge.
Gib für jedes Cluster eine sehr kurze sachliche Bezeichnung (maximal 8 Wörter) und die IDs der Artikel zurück.
Ein Artikel darf höchstens einem Cluster angehören. Erfinde keine Zusammenhänge.
""".strip()


def _extract_output_text(data: dict[str, Any]) -> str:
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    for output in data.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
            elif isinstance(text, dict):
                value = text.get("value")
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())
    return "\n".join(parts).strip()


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _recent_visible_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=TREND_WINDOW_HOURS)
    candidates: list[dict[str, Any]] = []
    for item in items:
        if item.get("visibility") != "visible":
            continue
        timestamp = _parse_dt(item.get("published_at")) or _parse_dt(item.get("fetched_at"))
        if timestamp and timestamp >= cutoff:
            candidates.append(item)
    return candidates


def _clear_trend_fields(items: list[dict[str, Any]]) -> None:
    for item in items:
        item["trend_level"] = ""
        item["trend_label"] = ""
        item["trend_source_count"] = 0
        item["trend_sources"] = []
        item["trend_cluster_id"] = ""


def apply_trending(items: list[dict[str, Any]]) -> tuple[int, str]:
    """Erkennt dasselbe konkrete Ereignis in mehreren Medien.

    Kennzeichnung:
      2 Quellen = multiple
      3 Quellen = trending
      4+ Quellen = breaking
    """
    _clear_trend_fields(items)
    candidates = _recent_visible_items(items)
    if len(candidates) < 2:
        return 0, ""

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MEDIA_MONITOR_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini")).strip()
    if not api_key:
        return 0, "Trending-Erkennung übersprungen: OPENAI_API_KEY ist nicht konfiguriert."

    compact = [
        {
            "id": str(item.get("id", "")),
            "source": str(item.get("source", "")),
            "published_at": str(item.get("published_at") or item.get("fetched_at") or ""),
            "title": str(item.get("title", ""))[:400],
            "summary": str(item.get("ai_summary") or item.get("teaser") or "")[:600],
        }
        for item in candidates
    ]

    payload = {
        "model": model,
        "input": [
            {"role": "developer", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"articles": compact}, ensure_ascii=False)},
        ],
        "reasoning": {"effort": "minimal"},
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "media_trend_clusters",
                "strict": True,
                "schema": TREND_SCHEMA,
            },
        },
        "max_output_tokens": 5000,
    }

    try:
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
    except requests.RequestException as exc:
        return 0, f"Trending-Erkennung nicht erreichbar: {exc}"

    if response.status_code >= 400:
        try:
            message = response.json().get("error", {}).get("message")
        except ValueError:
            message = None
        return 0, f"Trending-Erkennung: OpenAI-Fehler: {message or response.status_code}"

    try:
        raw_data = response.json()
        raw = _extract_output_text(raw_data)
        parsed = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        return 0, f"Trending-Erkennung konnte nicht gelesen werden: {exc}"

    by_id = {str(item.get("id")): item for item in candidates}
    used_ids: set[str] = set()
    cluster_count = 0

    for cluster_index, cluster in enumerate(parsed.get("clusters", []), start=1):
        if not isinstance(cluster, dict):
            continue
        ids = [str(value) for value in cluster.get("item_ids", []) if str(value) in by_id]
        ids = [item_id for item_id in ids if item_id not in used_ids]
        # Dieselbe Quelle zählt nur einmal; Ein-Quellen-Cluster sind kein Trend.
        source_map: dict[str, str] = {}
        valid_ids: list[str] = []
        for item_id in ids:
            source = str(by_id[item_id].get("source", "")).strip()
            if not source or source in source_map:
                continue
            source_map[source] = item_id
            valid_ids.append(item_id)
        if len(source_map) < 2:
            continue

        source_count = len(source_map)
        timestamps = [
            _parse_dt(by_id[item_id].get("published_at")) or _parse_dt(by_id[item_id].get("fetched_at"))
            for item_id in valid_ids
        ]
        timestamps = [value for value in timestamps if value is not None]
        span_hours = 999.0
        if len(timestamps) >= 2:
            span_hours = (max(timestamps) - min(timestamps)).total_seconds() / 3600.0

        # BREAKING ist bewusst strenger als bloß „mehrere Medien“:
        # mindestens 4 verschiedene Quellen innerhalb von 6 Stunden.
        # TRENDING: mindestens 3 verschiedene Quellen innerhalb von 12 Stunden.
        if source_count >= 4 and span_hours <= 6:
            level = "breaking"
        elif source_count >= 3 and span_hours <= 12:
            level = "trending"
        else:
            level = "multiple"
        sources = sorted(source_map.keys(), key=str.casefold)
        label = str(cluster.get("label") or "Mehrere Medien berichten").strip()[:100]
        cluster_id = f"trend-{cluster_index}-" + "-".join(sorted(valid_ids))[:80]

        for item_id in valid_ids:
            item = by_id[item_id]
            item["trend_level"] = level
            item["trend_label"] = label
            item["trend_source_count"] = source_count
            item["trend_sources"] = sources
            item["trend_cluster_id"] = cluster_id
            used_ids.add(item_id)
        cluster_count += 1

    return cluster_count, ""
