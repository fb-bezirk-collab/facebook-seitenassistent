from __future__ import annotations

from datetime import datetime, timezone

from app.comment_monitor.service import CommentMonitorService
from app.comment_monitor.storage import CommentStorage


storage = CommentStorage()


def mark_started() -> bool:
    current = storage.load_job()
    if current.get("state") == "running":
        return False
    storage.save_job({
        "state": "running",
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "finished_at": "",
        "new_count": 0,
        "seen_count": 0,
        "error_count": 0,
        "pages": [],
        "error": "",
    })
    return True


def run_fetch_job() -> None:
    try:
        result = CommentMonitorService().fetch_all()
        storage.save_job({
            "state": "success",
            "started_at": storage.load_job().get("started_at", ""),
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "new_count": result.get("new_count", 0),
            "seen_count": result.get("seen_count", 0),
            "error_count": result.get("error_count", 0),
            "pages": result.get("pages", []),
            "error": "",
        })
    except Exception as error:
        storage.save_job({
            "state": "error",
            "started_at": storage.load_job().get("started_at", ""),
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "new_count": 0,
            "seen_count": 0,
            "error_count": 1,
            "pages": [],
            "error": str(error),
        })
