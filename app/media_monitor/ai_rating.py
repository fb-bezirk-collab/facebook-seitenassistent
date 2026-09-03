from __future__ import annotations

import json
import os
from typing import Any

import requests


class MediaRatingError(RuntimeError):
    pass


API_URL = "https://api.openai.com/v1/responses"
SYSTEM_PROMPT = """
Du bewertest Meldungen österreichischer Medien für einen politischen Social-Media-Medienmonitor.
Bewerte nüchtern und ausschließlich anhand von Überschrift, Anreißer, Quelle und Quellenkategorie.
Erfinde keine Fakten. Eine hohe Bewertung bedeutet nicht Zustimmung, sondern politische Verwendbarkeit.

Bewerte jede Meldung von 0 bis 10 in diesen sechs Bereichen:
- political: politische Relevanz (Gewicht 25 %)
- people: unmittelbare Bedeutung für die Bevölkerung (20 %)
- profile: Bezug zu Migration/Asyl, Sicherheit, Teuerung, Steuern/Abgaben, Energie, EU,
  Gemeinden, Gesundheit/Pflege, Bildung, Verkehr, Landwirtschaft, Bürokratie,
  Meinungsfreiheit und Transparenz/Steuergeld (20 %)

REGIONALE REDAKTIONSPRIORITÄT DIESER APP:
- Bezirk Gänserndorf = höchste regionale Priorität.
- Weinviertel = höchste regionale Priorität.
- Niederösterreich = sehr hohe Priorität.
- Direkter FPÖ-/Freiheitlichen-Bezug in Niederösterreich, im Weinviertel oder im Bezirk Gänserndorf
  ist für diesen Medienmonitor grundsätzlich hoch relevant.
- Lokale/kommunale politische Meldungen aus diesen Gebieten dürfen nicht bloß deshalb niedriger
  bewertet werden, weil sie bundesweit weniger Reichweite haben.
- social: Eignung für einen klaren Social-Media-Beitrag (15 %)
- interest: öffentliches Interesse und Aufmerksamkeitspotenzial (10 %)
- reliable: Verwendbarkeit der vorliegenden Informationen; konkrete Meldung statt Spekulation (10 %)

Berechne total exakt nach diesen Gewichten und runde auf eine Dezimalstelle.
Ordne 1 bis 3 passende Kategorien zu. Mögliche Kategorien:
Migration, Asyl, Sicherheit, Kriminalität, Wirtschaft, Teuerung, Energie, EU, Gemeinden,
Niederösterreich, Bildung, Gesundheit, Pflege, Landwirtschaft, Umwelt, Verkehr, Justiz,
Steuern, Bürokratie, Transparenz, Soziales, Wohnen, Sonstiges.
Bestimme die Region nach dem tatsächlichen Ereignisort der Meldung, nicht nach dem Sitz des Mediums.
- Liegt der konkrete Vorgang in Österreich, nenne Österreich bzw. das erkennbare Bundesland/den Bezirk.
- Liegt er im EU-Ausland, nenne Land und – wenn klar erkennbar – Ort/Region, z. B. `Deutschland – Berlin (EU-Ausland)`, `Spanien – Ceuta (EU-Ausland)`.
- Liegt er außerhalb der EU, nenne Land/Ort mit dem Zusatz `(Ausland)`.
- Ist der Ort nicht zuverlässig erkennbar, verwende `Unklar`.
WICHTIG: Ein Ereignis im EU-Ausland kann für Österreich politisch sehr relevant sein und darf deshalb beim Relevanzscore nicht automatisch abgewertet werden. Ereignisort und Österreich-Relevanz sind getrennte Fragen.
summary: höchstens zwei kurze Sätze.
reason: ein kurzer Satz, warum die Meldung politisch brauchbar oder wenig brauchbar ist.
show: true nur bei total >= 6.5 und wenn es keine reine Sport-, Kultur-, Lifestyle-, Society-,
Unterhaltungs-, Reise-, Rezept- oder Horoskopmeldung ist.

Antworte ausschließlich als gültiges JSON:
{"ratings":[{"id":"...","political":0,"people":0,"profile":0,"social":0,"interest":0,"reliable":0,"total":0.0,"categories":["..."],"region":"...","summary":"...","reason":"...","show":false}]}
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
            # Responses API liefert Text typischerweise in content[].text.
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
            elif isinstance(text, dict):
                value = text.get("value")
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())
    return "\n".join(part for part in parts if part).strip()


def _response_refusal(data: dict[str, Any]) -> str:
    for output in data.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and content.get("type") == "refusal":
                refusal = content.get("refusal")
                if isinstance(refusal, str) and refusal.strip():
                    return refusal.strip()
    return ""


def _response_incomplete_reason(data: dict[str, Any]) -> str:
    details = data.get("incomplete_details")
    if isinstance(details, dict):
        reason = details.get("reason")
        if isinstance(reason, str):
            return reason.strip()
    return ""

def _clamp_score(value: Any) -> float:
    try:
        return max(0.0, min(10.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


RATING_SCHEMA = {
    "type": "object",
    "properties": {
        "ratings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "political": {"type": "number", "minimum": 0, "maximum": 10},
                    "people": {"type": "number", "minimum": 0, "maximum": 10},
                    "profile": {"type": "number", "minimum": 0, "maximum": 10},
                    "social": {"type": "number", "minimum": 0, "maximum": 10},
                    "interest": {"type": "number", "minimum": 0, "maximum": 10},
                    "reliable": {"type": "number", "minimum": 0, "maximum": 10},
                    "total": {"type": "number", "minimum": 0, "maximum": 10},
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "region": {"type": "string"},
                    "summary": {"type": "string"},
                    "reason": {"type": "string"},
                    "show": {"type": "boolean"}
                },
                "required": [
                    "id", "political", "people", "profile", "social", "interest",
                    "reliable", "total", "categories", "region", "summary", "reason", "show"
                ],
                "additionalProperties": False
            }
        }
    },
    "required": ["ratings"],
    "additionalProperties": False
}



FPÖ_TERMS = (
    "fpö", "fpoe", "freiheitlich", "freiheitliche", "kickl", "landbauer", "dorner",
)
GAENSERNDORF_TERMS = (
    "gänserndorf", "gaenserndorf", "marchegg", "angern an der march", "angern",
    "haringsee", "eckartsau", "orth an der donau", "orth/ donau", "orth/donau",
    "untersiebenbrunn", "leopoldsdorf im marchfelde", "leopoldsdorf",
    "matzen", "raggendorf", "velm-götzendorf", "velm-goetzendorf",
    "strasshof", "deutsch-wagram", "dürnkrut", "duernkrut", "auersthal",
    "drösing", "droesing", "prottes", "weikendorf", "zistersdorf",
    "marchfeld", "marchquerung",
)
WEINVIERTEL_TERMS = (
    "weinviertel", "mistelbach", "hollabrunn", "korneuburg",
)
NOE_TERMS = (
    "niederösterreich", "niederoesterreich", "nö ", " nö", "st. pölten",
)


def _priority_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key, "") or "").lower()
        for key in ("title", "teaser", "source_category", "url")
    )


def _apply_editorial_priority(item: dict[str, Any], rating: dict[str, Any]) -> dict[str, Any]:
    """Harte redaktionelle Mindestprioritäten für die regionale Ausgabe."""
    text = _priority_text(item)
    direct_fpoe = any(term in text for term in FPÖ_TERMS)
    gaenserndorf = any(term in text for term in GAENSERNDORF_TERMS)
    weinviertel = any(term in text for term in WEINVIERTEL_TERMS)
    noe = gaenserndorf or weinviertel or any(term in text for term in NOE_TERMS)

    result = dict(rating)
    categories = list(result.get("categories") or [])

    if gaenserndorf:
        result["profile"] = max(float(result.get("profile") or 0), 10.0)
        result["political"] = max(float(result.get("political") or 0), 8.0)
        result["social"] = max(float(result.get("social") or 0), 8.0)
        result["total"] = max(float(result.get("total") or 0), 8.0)
        result["show"] = True
        if "Niederösterreich" not in categories:
            categories.append("Niederösterreich")
        if result.get("region") in {"", "Unklar", "Österreich"}:
            result["region"] = "Bezirk Gänserndorf / Niederösterreich"

    elif weinviertel:
        result["profile"] = max(float(result.get("profile") or 0), 10.0)
        result["political"] = max(float(result.get("political") or 0), 7.5)
        result["total"] = max(float(result.get("total") or 0), 7.8)
        result["show"] = True
        if "Niederösterreich" not in categories:
            categories.append("Niederösterreich")
        if result.get("region") in {"", "Unklar", "Österreich"}:
            result["region"] = "Weinviertel / Niederösterreich"

    elif noe:
        result["profile"] = max(float(result.get("profile") or 0), 9.0)
        if direct_fpoe:
            result["political"] = max(float(result.get("political") or 0), 9.0)
            result["social"] = max(float(result.get("social") or 0), 8.5)
            result["total"] = max(float(result.get("total") or 0), 8.2)
            result["show"] = True
        elif float(result.get("total") or 0) >= 6.0:
            result["total"] = max(float(result.get("total") or 0), 6.8)
            result["show"] = True
        if "Niederösterreich" not in categories:
            categories.append("Niederösterreich")

    # FPÖ + Gänserndorf/Weinviertel ist für diese Ausgabe immer Spitzenrelevanz.
    if direct_fpoe and (gaenserndorf or weinviertel):
        result["political"] = max(float(result.get("political") or 0), 10.0)
        result["profile"] = 10.0
        result["social"] = max(float(result.get("social") or 0), 9.0)
        result["interest"] = max(float(result.get("interest") or 0), 8.0)
        result["total"] = max(float(result.get("total") or 0), 9.0)
        result["show"] = True
        result["reason"] = (
            "Direkter FPÖ-Bezug mit höchster regionaler Relevanz für "
            "Bezirk Gänserndorf/Weinviertel."
        )

    result["categories"] = categories[:3]
    return result


def rate_items(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not items:
        return {}

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MEDIA_MONITOR_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini")).strip()
    if not api_key:
        raise MediaRatingError("OPENAI_API_KEY ist nicht konfiguriert.")

    compact_items = [
        {
            "id": str(item.get("id", "")),
            "source": str(item.get("source", "")),
            "title": str(item.get("title", ""))[:500],
            "teaser": str(item.get("teaser", ""))[:1000],
            "source_category": str(item.get("source_category", ""))[:200],
        }
        for item in items
    ]

    payload = {
        "model": model,
        "input": [
            {"role": "developer", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"items": compact_items}, ensure_ascii=False)},
        ],
        "reasoning": {"effort": "minimal"},
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "media_monitor_ratings",
                "strict": True,
                "schema": RATING_SCHEMA,
            }
        },
        # Kleinere Batches plus großzügiges Limit verhindern abgeschnittene JSON-Antworten.
        # Bei GPT-5-Modellen zählt auch internes Reasoning in dieses Budget.
        "max_output_tokens": max(4000, min(8000, len(items) * 1000)),
    }

    try:
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
    except requests.RequestException as exc:
        raise MediaRatingError(f"OpenAI ist nicht erreichbar: {exc}") from exc

    if response.status_code >= 400:
        try:
            message = response.json().get("error", {}).get("message")
        except ValueError:
            message = None
        raise MediaRatingError(f"OpenAI-Fehler: {message or response.text.strip() or response.status_code}")

    try:
        data = response.json()
    except ValueError as exc:
        raise MediaRatingError("OpenAI hat keine gültige JSON-Antwort geliefert.") from exc

    refusal = _response_refusal(data)
    if refusal:
        raise MediaRatingError(f"OpenAI hat die Bewertung abgelehnt: {refusal}")

    incomplete_reason = _response_incomplete_reason(data)
    raw = _extract_output_text(data).strip()
    if incomplete_reason:
        preview = raw[:180].replace("\n", " ") if raw else "kein Ausgabetext"
        raise MediaRatingError(
            f"Die KI-Antwort war unvollständig ({incomplete_reason}). Antwortbeginn: {preview}"
        )
    if not raw:
        raise MediaRatingError("Die KI-Antwort enthielt keinen auswertbaren Text.")

    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        preview = raw[:180].replace("\n", " ")
        raise MediaRatingError(
            f"Die KI-Bewertung war kein gültiges JSON. Antwortbeginn: {preview}"
        ) from exc

    ratings = parsed.get("ratings", []) if isinstance(parsed, dict) else []
    result: dict[str, dict[str, Any]] = {}
    for rating in ratings:
        if not isinstance(rating, dict):
            continue
        item_id = str(rating.get("id", "")).strip()
        if not item_id:
            continue
        scores = {key: _clamp_score(rating.get(key)) for key in ("political", "people", "profile", "social", "interest", "reliable")}
        calculated_total = round(
            scores["political"] * 0.25 + scores["people"] * 0.20 + scores["profile"] * 0.20
            + scores["social"] * 0.15 + scores["interest"] * 0.10 + scores["reliable"] * 0.10,
            1,
        )
        categories = rating.get("categories", [])
        if not isinstance(categories, list):
            categories = []
        base_rating = {
            **scores,
            "total": calculated_total,
            "categories": [str(value).strip() for value in categories[:3] if str(value).strip()],
            "region": str(rating.get("region") or "Unklar").strip(),
            "summary": str(rating.get("summary") or "").strip(),
            "reason": str(rating.get("reason") or "").strip(),
            "show": calculated_total >= 6.5 and bool(rating.get("show", calculated_total >= 6.5)),
        }
        source_item = next((item for item in items if str(item.get("id", "")) == item_id), {})
        result[item_id] = _apply_editorial_priority(source_item, base_rating)
    return result
