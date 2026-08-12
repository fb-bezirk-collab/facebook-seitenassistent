from __future__ import annotations

from datetime import datetime, timezone
import math

from app.comment_monitor.ai import AI_CLASSIFICATION_VERSION, CommentAiError, classify_comments
from app.comment_monitor.storage import CommentStorage

storage = CommentStorage()
BLOCK_SIZE = 200
BATCH_SIZE = 12

def _eligible(c) -> bool:
    return c.status != "deleted" and bool((c.message or "").strip() or c.attachment_type or c.attachment_url or c.attachment_image_url)

def mark_ai_started(mode: str = "all") -> bool:
    current = storage.load_ai_job()
    if current.get("state") == "running":
        return False
    comments = storage.load()
    if mode == "errors":
        total = sum(1 for c in comments if _eligible(c) and bool(c.ai_error))
    else:
        total = sum(1 for c in comments if _eligible(c) and c.ai_version != AI_CLASSIFICATION_VERSION)
    storage.save_ai_job({
        "state": "running", "mode": mode,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "finished_at": "", "processed": 0, "failed": 0, "remaining": total,
        "total": total, "current_block": 0, "block_count": math.ceil(total / BLOCK_SIZE) if total else 0,
        "failures": [], "error": "",
    })
    return True

def _save_progress(*, processed: int, failed: int, remaining: int, total: int, block_no: int, failures: list[dict], state: str = "running", error: str = "") -> None:
    current = storage.load_ai_job()
    storage.save_ai_job({
        "state": state, "mode": current.get("mode", "all"),
        "started_at": current.get("started_at", ""),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds") if state != "running" else "",
        "processed": processed, "failed": failed, "remaining": remaining, "total": total,
        "current_block": block_no, "block_count": math.ceil(total / BLOCK_SIZE) if total else 0,
        "failures": failures[-50:], "error": error,
    })

def run_ai_job(mode: str = "all") -> None:
    processed = 0
    failed = 0
    failures: list[dict] = []
    try:
        comments = storage.load()
        if mode == "errors":
            pending = [c for c in comments if _eligible(c) and c.ai_error]
        else:
            pending = [c for c in comments if _eligible(c) and c.ai_version != AI_CLASSIFICATION_VERSION]
        total = len(pending)
        by_id = {c.comment_id: c for c in comments}

        for block_start in range(0, total, BLOCK_SIZE):
            block = pending[block_start:block_start + BLOCK_SIZE]
            block_no = block_start // BLOCK_SIZE + 1
            for batch_start in range(0, len(block), BATCH_SIZE):
                batch = block[batch_start:batch_start + BATCH_SIZE]
                text_batch = []
                # Reine Medienkommentare ohne Text werden zuverlässig markiert und nicht an die Text-KI geschickt.
                for c in batch:
                    c.ai_attempts += 1
                    if not (c.message or "").strip() and (c.attachment_type or c.attachment_url or c.attachment_image_url):
                        c.ai_category = "Medienkommentar"
                        c.ai_priority = "niedrig"
                        c.ai_recommendation = "Keine Aktion"
                        c.ai_reason = "Kommentar besteht nur aus einem Medienanhang; keine automatische Inhaltsbewertung ohne Bildanalyse."
                        c.ai_analyzed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                        c.ai_version = AI_CLASSIFICATION_VERSION
                        c.ai_error = ""
                        c.ai_error_at = ""
                        processed += 1
                    else:
                        text_batch.append(c)

                if text_batch:
                    payload = [{
                        "id": c.comment_id, "page": c.page_name, "post": c.post_message, "comment": c.message,
                        "attachment": c.attachment_type or ("Medienanhang" if (c.attachment_url or c.attachment_image_url) else ""),
                    } for c in text_batch]
                    try:
                        ratings = classify_comments(payload)
                        for c in text_batch:
                            rating = ratings.get(c.comment_id)
                            if not rating:
                                c.ai_error = "KI-Antwort enthielt für diesen Kommentar keine Bewertung."
                                c.ai_error_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                                failures.append({"comment_id": c.comment_id, "page": c.page_name, "reason": c.ai_error})
                                failed += 1
                                continue
                            c.ai_category = rating.get("category", "Neutral")
                            c.ai_priority = rating.get("priority", "niedrig")
                            c.ai_recommendation = rating.get("recommendation", "Ignorieren")
                            c.ai_reason = rating.get("reason", "")
                            c.ai_analyzed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                            c.ai_version = AI_CLASSIFICATION_VERSION
                            c.ai_error = ""
                            c.ai_error_at = ""
                            processed += 1
                    except CommentAiError as error:
                        for c in text_batch:
                            c.ai_error = str(error)
                            c.ai_error_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                            failures.append({"comment_id": c.comment_id, "page": c.page_name, "reason": str(error)})
                            failed += 1

                storage.save(list(by_id.values()))
                remaining = sum(1 for c in by_id.values() if _eligible(c) and c.ai_version != AI_CLASSIFICATION_VERSION)
                _save_progress(processed=processed, failed=failed, remaining=remaining, total=total, block_no=block_no, failures=failures)

        remaining = sum(1 for c in by_id.values() if _eligible(c) and c.ai_version != AI_CLASSIFICATION_VERSION)
        state = "success_with_errors" if failures else "success"
        _save_progress(processed=processed, failed=failed, remaining=remaining, total=total, block_no=math.ceil(total / BLOCK_SIZE) if total else 0, failures=failures, state=state)
    except Exception as error:
        _save_progress(processed=processed, failed=failed, remaining=0, total=storage.load_ai_job().get("total", 0), block_no=storage.load_ai_job().get("current_block", 0), failures=failures, state="error", error=str(error))
