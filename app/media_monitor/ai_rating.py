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
  Meinungsfreiheit, Transparenz/Steuergeld, Niederösterreich oder Bezirk Gänserndorf (20 %)
- social: Eignung für einen klaren Social-Media-Beitrag (15 %)
- interest: öffentliches Interesse und Aufmerksamkeitspotenzial (10 %)
- reliable: Verwendbarkeit der vorliegenden Informationen; konkrete Meldung statt Spekulation (10 %)

Berechne total exakt nach diesen Gewichten und runde auf eine Dezimalstelle.
Ordne 1 bis 3 passende Kategorien zu. Mögliche Kategorien:
Migration, Asyl, Sicherheit, Kriminalität, Wirtschaft, Teuerung, Energie, EU, Gemeinden,
Niederösterreich, Bildung, Gesundheit, Pflege, Landwirtschaft, Umwelt, Verkehr, Justiz,
Steuern, Bürokratie, Transparenz, Soziales, Wohnen, Sonstiges.
Bestimme die Region als Österreich, Niederösterreich, Wien, Burgenland, Steiermark,
Oberösterreich, Salzburg, Tirol, Vorarlberg, Kärnten, Bezirk Gänserndorf oder Unklar.
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
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"].strip())
    return "\n".join(part for part in parts if part).strip()


def _clamp_score(value: Any) -> float:
    try:
        return max(0.0, min(10.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


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
        "max_output_tokens": max(1800, min(7000, len(items) * 360)),
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
        raw = _extract_output_text(response.json()).strip()
        if raw.startswith("```"):
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise MediaRatingError("Die KI-Bewertung konnte nicht gelesen werden.") from exc

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
        result[item_id] = {
            **scores,
            "total": calculated_total,
            "categories": [str(value).strip() for value in categories[:3] if str(value).strip()],
            "region": str(rating.get("region") or "Unklar").strip(),
            "summary": str(rating.get("summary") or "").strip(),
            "reason": str(rating.get("reason") or "").strip(),
            "show": calculated_total >= 6.5 and bool(rating.get("show", calculated_total >= 6.5)),
        }
    return result
