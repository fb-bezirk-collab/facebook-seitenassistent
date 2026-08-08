from __future__ import annotations

import re
import unicodedata
from typing import Any


EXCLUDED_CATEGORY_TERMS = {
    "adabei", "auto", "beauty", "bundesliga", "computer", "digital", "esport",
    "film", "fitness", "formel 1", "freizeit", "fussball", "fußball", "games",
    "gesund leben", "horoskop", "kino", "kultur", "lifestyle", "mode", "motor",
    "musik", "promis", "ratgeber", "reise", "rezepte", "royals", "society",
    "sport", "stars", "style", "tennis", "tv", "unterhaltung", "urlaub",
}

EXCLUDED_URL_PARTS = {
    "/adabei/", "/auto/", "/digital/", "/freizeit/", "/horoskop/", "/kultur/",
    "/lifestyle/", "/motor/", "/reise/", "/sport/", "/stars-society/",
}

# Nur zur zusätzlichen Erkennung, wenn die Quellenkategorie fehlt oder unbrauchbar ist.
EXCLUDED_TITLE_PATTERNS = [
    r"\bchampions league\b", r"\bbundesliga\b", r"\bformel[ -]?1\b",
    r"\bgrand prix\b", r"\btennis\b", r"\bfußball\b", r"\bfussball\b",
    r"\bskispring", r"\bski-wm\b", r"\brezept\b", r"\bhoroskop\b",
    r"\broyal", r"\bpromi", r"\bschauspieler", r"\bsängerin?\b",
    r"\bmodel\b", r"\bbeauty\b", r"\bmode\b",
]

POLITICAL_SIGNAL_TERMS = {
    "regierung", "minister", "ministerin", "kanzler", "nationalrat", "landtag",
    "gemeinderat", "bürgermeister", "parlament", "gesetz", "verordnung", "eu",
    "europa", "asyl", "migration", "grenze", "polizei", "kriminalität",
    "steuer", "abgabe", "inflation", "teuerung", "energie", "pension", "pflege",
    "gesundheit", "schule", "bildung", "gemeinde", "budget", "defizit", "schulden",
    "förderung", "arbeitsmarkt", "arbeitslos", "landwirtschaft", "verkehr",
    "wohnen", "miete", "justiz", "gericht", "korruption", "transparenz",
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"\s+", " ", value).strip()


def classify_item(item: dict[str, Any]) -> tuple[str, str]:
    """Gibt ('excluded'|'candidate', Begründung) zurück."""
    title = _normalize(str(item.get("title", "")))
    teaser = _normalize(str(item.get("teaser", "")))
    category = _normalize(str(item.get("source_category", "")))
    url = _normalize(str(item.get("url", "")))

    matched_category = sorted(term for term in EXCLUDED_CATEGORY_TERMS if term in category)
    if matched_category:
        return "excluded", f"Regelfilter: Quellenkategorie '{matched_category[0]}' ausgeschlossen."

    matched_url = sorted(part for part in EXCLUDED_URL_PARTS if part in url)
    if matched_url:
        return "excluded", "Regelfilter: Ressort der Meldung ist ausgeschlossen."

    combined = f"{title} {teaser}"
    if any(re.search(pattern, combined, flags=re.IGNORECASE) for pattern in EXCLUDED_TITLE_PATTERNS):
        # Politische Artikel mit Sportbezug sollen nicht versehentlich verschwinden.
        if not any(signal in combined for signal in POLITICAL_SIGNAL_TERMS):
            return "excluded", "Regelfilter: Offensichtliche Sport-, Kultur- oder Lifestyle-Meldung."

    return "candidate", "Regelfilter bestanden; KI-Bewertung vorgesehen."
