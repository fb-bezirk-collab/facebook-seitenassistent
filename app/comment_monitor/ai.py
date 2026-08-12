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
    "Meinung/Kritik",
    "Provokation",
    "Beleidigung",
    "Drohung/Gewalt",
    "Spam",
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

AI_CLASSIFICATION_VERSION = "2.7.4"

CLASSIFICATION_PROMPT = r"""
Du bist Moderationsassistent für Facebook-Seiten einer politischen Organisation in Österreich.
Deine Aufgabe ist NICHT, negative oder scharfe politische Meinungen zu sanktionieren. Du sollst nur echten Moderationsbedarf herausfiltern.
Im Zweifel gilt: stehen lassen. Politische Meinungsfreiheit und robuste Debatte sind der Normalfall.

Wähle genau eine Kategorie:
- Zustimmung: überwiegend zustimmend oder unterstützend.
- Frage: echte Frage oder Informationswunsch.
- Meinung/Kritik: normale politische Meinung, Forderung, Ablehnung oder Kritik – auch scharf formuliert – solange keine echte Beschimpfung, Drohung oder reine Troll-Provokation vorliegt. Beispiele: „Rücktritt für alle fünf“, „Diese Regierung ist unfähig“, „Das gehört geändert“, „Die Partei gehört abgewählt“.
- Provokation: erkennbares Trollen, Spott oder Reizen ohne sachlichen Kern; noch keine klare Beschimpfung.
- Beleidigung: eindeutige persönliche Beschimpfung oder grob herabsetzende Bezeichnung. Beispiele sind direkte Schimpfwörter oder Beschimpfungen wie „Arschloch“, „Hurensohn“, „Volltrottel“, „Idioten“, „Gsindl“, „Dreckspack“, „Nazis“, „Faschisten“, „Volksverräter“. Begriffe wie „rechtsextrem“ nur dann hier einordnen, wenn sie erkennbar als pauschale persönliche Beschimpfung oder Herabsetzung verwendet werden; in einer sachlichen politischen Aussage bleibt es Meinung/Kritik.
- Drohung/Gewalt: konkrete oder sinngemäße Gewaltandrohung, Aufruf zu Gewalt, Todesdrohung oder vergleichbarer akuter Gefahreninhalt. Keine strafrechtliche Diagnose abgeben; nur den Moderationsbedarf markieren.
- Spam: Werbung, Scam, massenhaft irrelevanter Inhalt oder offensichtlich themenfremde Wiederholungen.
- Neutral: weder Zustimmung noch Frage noch erkennbare Kritik/Provokation/Moderationsbedarf.

PRIORITÄT – sehr zurückhaltend vergeben:
- hoch: NUR bei eindeutiger starker Beschimpfung, grob herabsetzenden Schimpfwörtern oder Etikettierungen, Drohung/Gewalt oder eindeutig gefährlichem Scam. Normale politische Kritik ist NIEMALS hoch.
- mittel: echte Frage mit Antwortbedarf, Provokation/Trolling oder gewöhnlicher Spam ohne akute Gefahr.
- niedrig: Zustimmung, Meinung/Kritik, neutrale Bemerkung oder sonst kein unmittelbarer Moderationsbedarf.

EMPFEHLUNG:
- Keine Aktion: Zustimmung oder neutrale Inhalte ohne Handlungsbedarf.
- Antworten: echte Frage, wenn eine Antwort sinnvoll ist.
- Antwort optional: sachliche/politische Kritik, wenn eine Reaktion kommunikativ nützen könnte.
- Ignorieren: normale Kritik/Forderung oder Provokation, bei der eine Reaktion keinen Nutzen bringt.
- Ausblenden prüfen: NUR bei klarer Beleidigung oder hartnäckiger Provokation.
- Löschen prüfen: NUR bei Drohung/Gewalt, schwerer Beschimpfung, Scam/Spam oder ähnlich eindeutig problematischem Inhalt. Nie automatisch löschen.

WICHTIGE REGELN:
1. Kritik an Parteien, Politikern, Regierungen oder politischen Entscheidungen ist grundsätzlich zulässig und darf nicht allein deshalb als Beleidigung oder hoher Moderationsbedarf gelten.
2. Forderungen wie „Rücktritt“, „abgewählt gehören“ oder „in der Regierung nicht brauchen“ sind Meinung/Kritik, nicht Beleidigung.
3. Negative Stimmung, mehrere Daumen-runter-Emojis, Sarkasmus oder Ärger reichen NICHT für Priorität hoch.
4. Eine rechtliche oder strafrechtliche Bewertung ist nicht deine Aufgabe. Verwende niemals Aussagen wie „strafbar“, „illegal“ oder „Anzeige erstatten“, außer dies wird ausdrücklich im Kommentar selbst thematisiert.
5. Erfinde keine Absichten oder Tatsachen. Berücksichtige Kommentar und zugehörigen Beitrag. Begründe die Einstufung in einem kurzen Satz.
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
        })

    parsed = _call(
        CLASSIFICATION_PROMPT,
        {"comments": compact},
        "facebook_comment_classification",
        CLASSIFICATION_SCHEMA,
        max(3000, min(7000, len(compact) * 500)),
    )
    comment_text_by_id = {str(item.get("id", "")): str(item.get("comment", "")).lower() for item in compact}
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
        comment_text = comment_text_by_id.get(comment_id, "")

        # Häufige politische Forderungen wie "Rücktritt" sind ausdrücklich keine
        # Beleidigung, solange keine echte Beschimpfung oder Drohung dazukommt.
        political_demand_markers = (
            "rücktritt", "zurücktreten", "abgewählt", "abwahl",
            "in der regierung nicht brauchen", "gehört abgewählt",
        )
        strong_abuse_markers = (
            "arschloch", "hurensohn", "volltrottel", "trottel", "idiot", "idioten",
            "gsindl", "dreckspack", "nazi", "nazis", "faschist", "faschisten",
            "volksverräter", "rechtsextrem",
        )
        threat_markers = (
            "umbringen", "töten", "erschießen", "erschiessen", "abstechen",
            "aufhängen", "aufhaengen", "anzünden", "anzuenden", "totmachen",
        )
        has_political_demand = any(marker in comment_text for marker in political_demand_markers)
        has_strong_abuse = any(marker in comment_text for marker in strong_abuse_markers)
        has_threat = any(marker in comment_text for marker in threat_markers)
        if has_political_demand and not has_strong_abuse and not has_threat and category in {"Beleidigung", "Provokation"}:
            category = "Meinung/Kritik"
            priority = "niedrig"
            recommendation = "Ignorieren"

        # Harte Sicherheitsregel gegen Übermoderation: Nur eindeutige Problemkategorien
        # dürfen Priorität "hoch" erhalten. Normale politische Kritik bleibt niedrig.
        if category not in {"Beleidigung", "Drohung/Gewalt", "Spam"} and priority == "hoch":
            priority = "mittel" if category in {"Frage", "Provokation"} else "niedrig"
        if category == "Meinung/Kritik":
            priority = "niedrig"
            if recommendation in {"Ausblenden prüfen", "Löschen prüfen"}:
                recommendation = "Ignorieren"
        elif category == "Zustimmung" or category == "Neutral":
            priority = "niedrig"
            if recommendation in {"Ausblenden prüfen", "Löschen prüfen"}:
                recommendation = "Keine Aktion"
        elif category == "Frage" and priority == "hoch":
            priority = "mittel"
        elif category == "Provokation" and priority == "hoch":
            priority = "mittel"

        result[comment_id] = {
            "category": category,
            "priority": priority,
            "recommendation": recommendation,
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
