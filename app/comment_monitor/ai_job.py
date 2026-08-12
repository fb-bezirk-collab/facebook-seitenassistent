from __future__ import annotations

from datetime import datetime, timezone

from app.comment_monitor.ai import AI_CLASSIFICATION_VERSION, CommentAiError, classify_comments
from app.comment_monitor.storage import CommentStorage


storage = CommentStorage()


def mark_ai_started() -> bool:
    current = storage.load_ai_job()
    if current.get("state") == "running":
        return False
    storage.save_ai_job({
        "state": "running",
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "finished_at": "",
        "processed": 0,
        "remaining": 0,
        "error": "",
    })
    return True


def run_ai_job() -> None:
    processed = 0
    try:
        comments = storage.load()
        pending = [
            c for c in comments
            if c.status != "deleted" and c.ai_version != AI_CLASSIFICATION_VERSION and (c.message or "").strip()
        ]
        # Sicherheitsgrenze für einen einzelnen Hintergrundlauf. Weitere unbewertete
        # Kommentare können mit einem weiteren Klick verarbeitet werden.
        pending = pending[:200]
        by_id = {c.comment_id: c for c in comments}

        for start in range(0, len(pending), 12):
            batch = pending[start:start + 12]
            payload = [
                {
                    "id": c.comment_id,
                    "page": c.page_name,
                    "post": c.post_message,
                    "comment": c.message,
                }
                for c in batch
            ]
            ratings = classify_comments(payload)
            for comment_id, rating in ratings.items():
                comment = by_id.get(comment_id)
                if comment is None:
                    continue
                comment.ai_category = rating.get("category", "Neutral")
                comment.ai_priority = rating.get("priority", "niedrig")
                comment.ai_recommendation = rating.get("recommendation", "Ignorieren")
                comment.ai_reason = rating.get("reason", "")
                comment.ai_analyzed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                comment.ai_version = AI_CLASSIFICATION_VERSION
                processed += 1
            storage.save(list(by_id.values()))

        all_comments = storage.load()
        remaining = sum(
            1 for c in all_comments
            if c.status != "deleted" and c.ai_version != AI_CLASSIFICATION_VERSION and (c.message or "").strip()
        )
        storage.save_ai_job({
            "state": "success",
            "started_at": storage.load_ai_job().get("started_at", ""),
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "processed": processed,
            "remaining": remaining,
            "error": "",
        })
    except (CommentAiError, Exception) as error:
        storage.save_ai_job({
            "state": "error",
            "started_at": storage.load_ai_job().get("started_at", ""),
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "processed": processed,
            "remaining": 0,
            "error": str(error),
        })
