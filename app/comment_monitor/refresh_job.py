from __future__ import annotations

from datetime import datetime, timezone

from app.comment_monitor.service import CommentMonitorService
from app.comment_monitor.storage import CommentStorage


storage = CommentStorage()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mark_refresh_started() -> bool:
    current = storage.load_refresh_job()
    if current.get("state") == "running":
        return False

    total = len([c for c in storage.load() if c.status != "deleted"])
    storage.save_refresh_job({
        "state": "running",
        "started_at": _now(),
        "finished_at": "",
        "total": total,
        "processed": 0,
        "updated": 0,
        "media_found": 0,
        "preview_found": 0,
        "author_found": 0,
        "errors": 0,
        "last_error": "",
    })
    return True


def run_refresh_job() -> None:
    started_at = storage.load_refresh_job().get("started_at", "")

    def progress(data: dict) -> None:
        payload = {
            "state": "running",
            "started_at": started_at,
            "finished_at": "",
            **data,
        }
        storage.save_refresh_job(payload)

    try:
        result = CommentMonitorService().refresh_existing(progress_callback=progress)
        storage.save_refresh_job({
            "state": "success" if not result.get("errors") else "success_with_errors",
            "started_at": started_at,
            "finished_at": _now(),
            **result,
        })
    except Exception as error:
        previous = storage.load_refresh_job()
        storage.save_refresh_job({
            **previous,
            "state": "error",
            "finished_at": _now(),
            "last_error": str(error),
        })
