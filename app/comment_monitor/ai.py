from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests


API_URL = "https://api.openai.com/v1/responses"


class CommentAiError(RuntimeError):
    pass


CATEGORIES = (
    "Zustimmung",
    "Frage",
    "Meinung/Kritik",
    "Provokation",
    "Beleidigung",
    "Drohung/Gewalt",
    "Spam",
    "Off-Topic",
    "Medienkommentar",
    "Neutral",
)

RECOMMENDATIONS = (
    "Keine Aktion",
    "Antworten",
    "Antwort optional",
    "Ignorieren",
    "Ausblenden prüfen",
    "Löschen prüfen",
)

AI_CLASSIFICATION_VERSION = "3.3.16"

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_moderation_profile() -> str:
    path = PROJECT_ROOT / "profiles" / "comment_moderation.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise CommentAiError("Moderationsprofil konnte nicht geladen werden: profiles/comment_moderation.md") from exc


def _classification_prompt() -> str:
    return (
        "Du bewertest Facebook-Kommentare für den Moderations-Monitor einer politischen Seite in Österreich.\\n"
        "Halte dich strikt an das folgende Moderationsprofil. Es hat Vorrang vor allgemeinen Annahmen über Tonfall oder Negativität.\\n\\n"
        + _load_moderation_profile()
        + "\\n\\nGib ausschließlich die verlangte strukturierte JSON-Antwort zurück."
    )


CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "priority": {"type": "string", "enum": ["hoch", "mittel", "niedrig"]},
                    "recommendation": {"type": "string", "enum": list(RECOMMENDATIONS)},
                    "reason": {"type": "string"},
                },
                "required": ["id", "category", "priority", "recommendation", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

REPLY_PROMPT = """
Du bist Social-Media-Redakteur für eine österreichische politische Facebook-Seite.
Erstelle genau einen kurzen Antwortvorschlag auf den Nutzerkommentar.

Regeln:
- Antworte auf den tatsächlichen Kommentar und berücksichtige den zugehörigen Beitrag.
- Österreichisches Standarddeutsch, kein Gendern.
- Klar, verständlich und möglichst kurz (meist 1 bis 4 Sätze).
- Bei Zustimmung: freundlich und knapp bedanken, wenn eine Antwort sinnvoll ist.
- Bei Fragen: konkret antworten, aber keine Fakten erfinden. Wenn die nötige Information fehlt, offen sagen, dass sie aus dem vorliegenden Beitrag nicht hervorgeht.
- Bei Meinung/Kritik: sachlich, selbstbewusst, nicht defensiv; eine Antwort ist oft nicht nötig.
- Bei Provokation: nicht eskalieren und nicht persönlich werden.
- Bei Beleidigung, Drohung/Gewalt oder Spam: keinen aggressiven Gegenschlag formulieren; wenn eine Antwort unklug wäre, weise knapp darauf hin, dass keine Antwort empfohlen wird.
- Keine erfundenen Zahlen, Namen, Zitate, Beschlüsse oder Rechtsbehauptungen.
- Keine Behauptung über Motive oder persönliche Eigenschaften des Kommentierenden.

Zusätzlich gib einen kurzen Stilhinweis aus.
""".strip()

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "style": {"type": "string"},
    },
    "required": ["reply", "style"],
    "additionalProperties": False,
}


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


def _call(prompt: str, payload_data: dict[str, Any], schema_name: str, schema: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv(
        "OPENAI_COMMENT_MONITOR_MODEL",
        os.getenv("OPENAI_MEDIA_MONITOR_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini")),
    ).strip()
    if not api_key:
        raise CommentAiError("OPENAI_API_KEY ist nicht konfiguriert.")

    request_payload = {
        "model": model,
        "input": [
            {"role": "developer", "content": prompt},
            {"role": "user", "content": json.dumps(payload_data, ensure_ascii=False)},
        ],
        "reasoning": {"effort": "minimal"},
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        },
        "max_output_tokens": max_tokens,
    }

    try:
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=request_payload,
            timeout=120,
        )
    except requests.RequestException as exc:
        raise CommentAiError(f"OpenAI ist nicht erreichbar: {exc}") from exc

    if response.status_code >= 400:
        try:
            message = response.json().get("error", {}).get("message")
        except ValueError:
            message = None
        raise CommentAiError(f"OpenAI-Fehler: {message or response.status_code}")

    try:
        data = response.json()
        raw = _extract_output_text(data)
        parsed = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise CommentAiError("Die KI-Antwort konnte nicht als gültiges JSON gelesen werden.") from exc

    if not isinstance(parsed, dict):
        raise CommentAiError("Die KI-Antwort hatte ein unerwartetes Format.")
    return parsed


def classify_comments(items: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    if not items:
        return {}
    compact = []
    for item in items:
        compact.append({
            "id": str(item.get("id", "")),
            "page": str(item.get("page", ""))[:200],
            "post": str(item.get("post", ""))[:1400],
            "comment": str(item.get("comment", ""))[:1800],
            "attachment": str(item.get("attachment", ""))[:300],
        })

    parsed = _call(
        _classification_prompt(),
        {"comments": compact},
        "facebook_comment_classification",
        CLASSIFICATION_SCHEMA,
        max(3000, min(7000, len(compact) * 500)),
    )
    result: dict[str, dict[str, str]] = {}
    for row in parsed.get("items", []):
        if not isinstance(row, dict):
            continue
        comment_id = str(row.get("id", "")).strip()
        if not comment_id:
            continue
        category = str(row.get("category", "Neutral"))
        priority = str(row.get("priority", "niedrig"))
        recommendation = str(row.get("recommendation", "Ignorieren"))
        reason = str(row.get("reason", "")).strip()

        # Sicherheitsnetz gegen Übermoderation: Zustimmung/Neutral sowie normale
        # politische Kritik dürfen nicht mit einer Moderationsempfehlung zurückkommen.
        if category in {"Zustimmung", "Neutral"}:
            priority = "niedrig"
            if recommendation in {"Ausblenden prüfen", "Löschen prüfen"}:
                recommendation = "Keine Aktion"
        elif category in {"Meinung/Kritik", "Off-Topic"}:
            priority = "niedrig"
            if recommendation in {"Ausblenden prüfen", "Löschen prüfen"}:
                recommendation = "Ignorieren"
        elif category == "Frage" and priority == "hoch":
            priority = "mittel"

        result[comment_id] = {
            "category": category,
            "priority": priority,
            "recommendation": recommendation,
            "reason": reason,
        }
    return result


def suggest_reply(item: dict[str, str]) -> dict[str, str]:
    parsed = _call(
        REPLY_PROMPT,
        {
            "page": str(item.get("page", ""))[:200],
            "post": str(item.get("post", ""))[:1800],
            "comment": str(item.get("comment", ""))[:1800],
            "attachment": str(item.get("attachment", ""))[:300],
            "category": str(item.get("category", "")),
            "priority": str(item.get("priority", "")),
            "recommendation": str(item.get("recommendation", "")),
        },
        "facebook_comment_reply_suggestion",
        REPLY_SCHEMA,
        1800,
    )
    return {
        "reply": str(parsed.get("reply", "")).strip(),
        "style": str(parsed.get("style", "")).strip(),
    }
