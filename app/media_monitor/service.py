from __future__ import annotations

from app.media_monitor.ai_rating import MediaRatingError, rate_items
from app.media_monitor.fetchers import (
    fetch_apa,
    fetch_exxpress,
    fetch_fob,
    fetch_heute,
    fetch_kleine,
    fetch_krone,
    fetch_kurier,
    fetch_nfz,
    fetch_nius_at,
    fetch_noen,
    fetch_oe24,
    fetch_orf,
    fetch_presse,
    fetch_sn,
    fetch_standard,
    fetch_unzensuriert,
    fetch_zurzeit,
)
from app.media_monitor.prefilter import classify_item
from app.media_monitor.storage import load_items, merge_fetched_items, save_items
from app.media_monitor.trending import apply_trending


AI_BATCH_SIZE = 5
SOURCE_FETCHERS = (
    ("Krone", fetch_krone),
    ("Kurier", fetch_kurier),
    ("Heute", fetch_heute),
    ("oe24", fetch_oe24),
    ("ORF", fetch_orf),
    ("Der Standard", fetch_standard),
    ("Die Presse", fetch_presse),
    ("exxpress", fetch_exxpress),
    ("Salzburger Nachrichten", fetch_sn),
    ("Kleine Zeitung", fetch_kleine),
    ("NÖN", fetch_noen),
    ("APA (öffentlich)", fetch_apa),
    ("Unzensuriert", fetch_unzensuriert),
    ("NIUS Österreich", fetch_nius_at),
    ("FoB News", fetch_fob),
    ("ZurZeit", fetch_zurzeit),
    ("NFZ", fetch_nfz),
)


def _apply_prefilter(items: list[dict]) -> tuple[int, list[dict]]:
    excluded_count = 0
    candidates: list[dict] = []
    for item in items:
        # Bereits manuell bearbeitete Datensätze werden nicht verändert.
        if item.get("status") in {"saved", "approved", "rejected", "draft_created"}:
            continue
        status, reason = classify_item(item)
        item["prefilter_status"] = status
        item["prefilter_reason"] = reason
        if status == "excluded":
            item["visibility"] = "filtered_rule"
            item["category"] = "Ausgefiltert"
            item["ai_reason"] = reason
            item["score_total"] = None
            excluded_count += 1
        else:
            # Auch Altbestände ohne Bewertung werden erfasst.
            if item.get("score_total") is None:
                candidates.append(item)
    return excluded_count, candidates


def _apply_ratings(items: list[dict], candidates: list[dict]) -> tuple[int, int, str]:
    rated_count = 0
    visible_count = 0
    error_message = ""
    by_id = {str(item.get("id")): item for item in items}

    for start in range(0, len(candidates), AI_BATCH_SIZE):
        batch = candidates[start:start + AI_BATCH_SIZE]
        try:
            ratings = rate_items(batch)
        except MediaRatingError as exc:
            error_message = str(exc)
            break

        for item_id, rating in ratings.items():
            item = by_id.get(item_id)
            if not item:
                continue
            item["score_political"] = rating["political"]
            item["score_people"] = rating["people"]
            item["score_profile"] = rating["profile"]
            item["score_social"] = rating["social"]
            item["score_interest"] = rating["interest"]
            item["score_reliable"] = rating["reliable"]
            item["score_total"] = rating["total"]
            item["categories"] = rating["categories"]
            item["category"] = ", ".join(rating["categories"]) or "Sonstiges"
            item["region"] = rating["region"]
            item["ai_summary"] = rating["summary"]
            item["ai_reason"] = rating["reason"]
            item["visibility"] = "visible" if rating["show"] else "filtered_score"
            rated_count += 1
            if rating["show"]:
                visible_count += 1

    return rated_count, visible_count, error_message


def fetch_current_media() -> dict:
    source_results: list[dict] = []
    total_new = 0
    successful_sources = 0

    # Jede Quelle läuft unabhängig. Ein Fehler bei einer Seite blockiert die anderen nicht.
    for source_name, fetcher in SOURCE_FETCHERS:
        try:
            fetched = fetcher()
            _, new_count = merge_fetched_items(fetched)
            total_new += new_count
            successful_sources += 1
            source_results.append({
                "source": source_name,
                "fetched_count": len(fetched),
                "new_count": new_count,
                "error": "",
            })
        except Exception as exc:
            message = str(exc).strip() or "Unbekannter Abruffehler."
            print(f"Fehler beim Abruf von {source_name}: {exc}", flush=True)
            source_results.append({
                "source": source_name,
                "fetched_count": 0,
                "new_count": 0,
                "error": message,
            })

    if successful_sources == 0:
        details = "; ".join(f"{entry['source']}: {entry['error']}" for entry in source_results)
        raise RuntimeError("Keine Medienquelle konnte abgerufen werden. " + details)

    items = load_items()
    excluded_count, candidates = _apply_prefilter(items)
    rated_count, visible_count, rating_error = _apply_ratings(items, candidates)
    trend_count, trend_error = apply_trending(items)
    save_items(items)

    source_errors = [entry for entry in source_results if entry["error"]]
    source_warning = " | ".join(
        f"{entry['source']}: {entry['error']}" for entry in source_errors
    )
    warnings = [message for message in (source_warning, rating_error, trend_error) if message]

    return {
        "items": items,
        "new_count": total_new,
        "excluded_count": excluded_count,
        "rated_count": rated_count,
        "visible_count": visible_count,
        "trend_count": trend_count,
        "rating_error": " | ".join(warnings),
        "source_results": source_results,
    }
