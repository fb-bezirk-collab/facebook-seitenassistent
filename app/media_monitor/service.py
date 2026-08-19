from __future__ import annotations

import os

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


DEBUG_TARGETS = {
    "Krone": os.getenv("KRONE_DEBUG_TARGET", "4259228").strip(),
    "Die Presse": os.getenv("PRESSE_DEBUG_TARGET", "41178205").strip(),
}

def _debug_has_target(items: list[dict], target: str) -> bool:
    return bool(target) and any(target in str(item.get("url") or "") for item in items)

class MediaFetchCancelled(RuntimeError):
    """Interner Kontrollfluss für einen vom Benutzer abgebrochenen Medienabruf."""


def _check_cancel(should_cancel) -> None:
    if should_cancel is not None and should_cancel():
        raise MediaFetchCancelled("Medienabruf wurde abgebrochen.")


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


def _apply_ratings(items: list[dict], candidates: list[dict], should_cancel=None, progress_callback=None) -> tuple[int, int, str]:
    rated_count = 0
    visible_count = 0
    error_message = ""
    by_id = {str(item.get("id")): item for item in items}

    total_batches = max(1, (len(candidates) + AI_BATCH_SIZE - 1) // AI_BATCH_SIZE)
    for batch_index, start in enumerate(range(0, len(candidates), AI_BATCH_SIZE), start=1):
        _check_cancel(should_cancel)
        if progress_callback:
            progress_callback(
                62 + int(((batch_index - 1) / total_batches) * 32),
                f"KI-Bewertung: Paket {batch_index} von {total_batches}",
            )
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


def fetch_current_media(should_cancel=None, progress_callback=None) -> dict:
    source_results: list[dict] = []
    total_new = 0
    successful_sources = 0

    total_sources = len(SOURCE_FETCHERS)
    if progress_callback:
        progress_callback(2, f"Quellenabruf wird gestartet (0 von {total_sources})")

    # Jede Quelle läuft unabhängig. Ein Fehler bei einer Seite blockiert die anderen nicht.
    for source_index, (source_name, fetcher) in enumerate(SOURCE_FETCHERS, start=1):
        if progress_callback:
            progress_callback(2 + int(((source_index - 1) / total_sources) * 53), f"Quelle {source_index} von {total_sources}: {source_name}")
        _check_cancel(should_cancel)
        try:
            fetched = fetcher()
            _check_cancel(should_cancel)
            debug_target = DEBUG_TARGETS.get(source_name, "")
            if debug_target:
                print(
                    f"MEDIA DEBUG | {source_name} | Fetcher-Rückgabe={len(fetched)} | "
                    f"Target {debug_target} vorhanden={_debug_has_target(fetched, debug_target)}",
                    flush=True,
                )
            _, new_count = merge_fetched_items(fetched)
            if debug_target:
                stored_now = load_items()
                print(
                    f"MEDIA DEBUG | {source_name} | nach merge_fetched_items | "
                    f"Target {debug_target} im Storage={_debug_has_target(stored_now, debug_target)} | "
                    f"new_count={new_count}",
                    flush=True,
                )
            total_new += new_count
            successful_sources += 1
            source_results.append({
                "source": source_name,
                "fetched_count": len(fetched),
                "new_count": new_count,
                "error": "",
            })
        except MediaFetchCancelled:
            raise
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

    _check_cancel(should_cancel)
    if progress_callback:
        progress_callback(58, "Quellen abgeschlossen · Regel-Filter wird angewendet")
    items = load_items()
    excluded_count, candidates = _apply_prefilter(items)
    _check_cancel(should_cancel)
    if progress_callback:
        progress_callback(62, f"KI-Bewertung wird gestartet ({len(candidates)} Meldungen)")
    rated_count, visible_count, rating_error = _apply_ratings(items, candidates, should_cancel, progress_callback)
    _check_cancel(should_cancel)
    if progress_callback:
        progress_callback(96, "Medienübergreifende Themen werden erkannt")
    trend_count, trend_error = apply_trending(items)
    if progress_callback:
        progress_callback(99, "Ergebnisse werden gespeichert")
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
