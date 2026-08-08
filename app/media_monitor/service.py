from __future__ import annotations

from app.media_monitor.ai_rating import MediaRatingError, rate_items
from app.media_monitor.fetchers.krone import fetch_krone
from app.media_monitor.prefilter import classify_item
from app.media_monitor.storage import merge_fetched_items, save_items


AI_BATCH_SIZE = 5


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
    fetched = fetch_krone()
    items, new_count = merge_fetched_items(fetched)
    excluded_count, candidates = _apply_prefilter(items)
    rated_count, visible_count, rating_error = _apply_ratings(items, candidates)
    save_items(items)
    return {
        "items": items,
        "new_count": new_count,
        "excluded_count": excluded_count,
        "rated_count": rated_count,
        "visible_count": visible_count,
        "rating_error": rating_error,
    }
