from __future__ import annotations

import json
import os
from typing import Any

import requests


API_URL = "https://api.openai.com/v1/responses"


class CommentAiError(RuntimeError):
    pass


CATEGORIES = (
    "Zustimmung",
    "Frage",
    "Sachliche Kritik",
    "Politische Kritik",
    "Provokation",
    "Beleidigung",
    "Spam",
    "Neutral",
)

RECOMMENDATIONS = (
    "Antworten",
    "Ignorieren",
    "Ausblenden prüfen",
    "Löschen prüfen",
)

CLASSIFICATION_PROMPT = """
Du bist Moderationsassistent für Facebook-Seiten einer politischen Organisation in Österreich.
Ordne Kommentare nüchtern ein. Die Einordnung ist eine Arbeitshilfe und keine automatische Moderationsentscheidung.

Wähle genau eine Kategorie:
- Zustimmung: überwiegend zustimmend/unterstützend.
- Frage: echte Frage oder Informationswunsch.
- Sachliche Kritik: inhaltliche Kritik ohne primär parteipolitischen Angriff.
- Politische Kritik: politische Gegenposition oder Kritik an Partei/Funktionären/Beitrag.
- Provokation: erkennbar auf Reizung, Spott oder Eskalation angelegt, ohne primär sachliche Auseinandersetzung.
- Beleidigung: persönliche Herabsetzung, Beschimpfung oder grob abwertende Ansprache.
- Spam: Werbung, Scam, massenhaft irrelevanter Inhalt oder offensichtlich themenfremd.
- Neutral: passt in keine der anderen Kategorien.

Priorität:
- hoch: akuter Moderationsbedarf, Drohung, starke Beleidigung, Spam/Scam, eskalierende Provokation oder wichtige direkte Frage.
- mittel: normale Frage, sachliche/politische Kritik oder moderater Konflikt.
- niedrig: Zustimmung, neutrale Bemerkung oder ohne Handlungsbedarf.

Empfehlung:
- Antworten: wenn eine sinnvolle Reaktion voraussichtlich nützt.
- Ignorieren: wenn keine Reaktion nötig ist.
- Ausblenden prüfen: bei Provokation/Beleidigung, wenn Ausblenden erwogen werden sollte.
- Löschen prüfen: nur bei klar schwerwiegendem Inhalt wie Spam/Scam, Drohung oder gravierender Beleidigung. Nie automatisch löschen.

Erfinde keine Absichten oder Tatsachen. Berücksichtige Kommentar und zugehörigen Beitrag. Begründe die Einstufung in einem kurzen Satz.
""".strip()

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
- Bei Kritik: sachlich, selbstbewusst, nicht defensiv.
- Bei Provokation: nicht eskalieren und nicht persönlich werden.
- Bei Beleidigung/Spam: keinen aggressiven Gegenschlag formulieren; wenn eine Antwort unklug wäre, gib trotzdem einen neutralen sehr kurzen Vorschlag oder weise darauf hin, dass keine Antwort empfohlen wird.
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
        })

    parsed = _call(
        CLASSIFICATION_PROMPT,
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
        result[comment_id] = {
            "category": str(row.get("category", "Neutral")),
            "priority": str(row.get("priority", "niedrig")),
            "recommendation": str(row.get("recommendation", "Ignorieren")),
            "reason": str(row.get("reason", "")).strip(),
        }
    return result


def suggest_reply(item: dict[str, str]) -> dict[str, str]:
    parsed = _call(
        REPLY_PROMPT,
        {
            "page": str(item.get("page", ""))[:200],
            "post": str(item.get("post", ""))[:1800],
            "comment": str(item.get("comment", ""))[:1800],
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
