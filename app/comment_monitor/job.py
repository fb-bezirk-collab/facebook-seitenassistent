from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from app.comment_monitor.service import CommentFetchCancelled, CommentMonitorService
from app.comment_monitor.storage import CommentStorage


storage = CommentStorage()
_LOCK = threading.RLock()
_CANCEL_EVENT = threading.Event()
_ACTIVE_JOB_ID: str | None = None
STALE_GRACE_SECONDS = 90


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _age_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
    except (TypeError, ValueError):
        return None


def _read_raw() -> dict:
    return storage.load_job()


def load_status() -> dict:
    """Lädt den Jobstatus und heilt Running-Zustände nach Railway-Restarts."""
    data = _read_raw()
    state = str(data.get("state") or "idle")
    job_id = str(data.get("job_id") or "")
    age = _age_seconds(data.get("started_at"))
    if state in {"running", "cancel_requested"}:
        with _LOCK:
            active_here = bool(_ACTIVE_JOB_ID and job_id and _ACTIVE_JOB_ID == job_id)
        if not active_here and (age is None or age > STALE_GRACE_SECONDS):
            healed = {**data, "finished_at": _now_iso()}
            if state == "cancel_requested":
                healed.update({"state": "cancelled", "message": "Der Kommentarabruf wurde beendet."})
            else:
                healed.update({
                    "state": "error",
                    "error": (
                        "Der vorige Kommentarabruf wurde unterbrochen – vermutlich durch einen "
                        "Railway-Neustart oder einen abgebrochenen Worker. Du kannst den Abruf jetzt neu starten."
                    ),
                })
            storage.save_job(healed)
            return healed
    return data


def mark_started() -> str | None:
    global _ACTIVE_JOB_ID
    with _LOCK:
        current = load_status()
        if _ACTIVE_JOB_ID or current.get("state") in {"running", "cancel_requested"}:
            return None
        job_id = uuid.uuid4().hex
        _CANCEL_EVENT.clear()
        storage.save_job({
            "state": "running",
            "job_id": job_id,
            "started_at": _now_iso(),
            "finished_at": "",
            "page_index": 0,
            "page_count": 0,
            "page_name": "",
            "stage": "Kommentarabruf wird gestartet",
            "new_count": 0,
            "seen_count": 0,
            "error_count": 0,
            "pages": [],
            "error": "",
        })
        return job_id


def _is_cancel_requested(job_id: str) -> bool:
    if _CANCEL_EVENT.is_set():
        return True
    current = _read_raw()
    return str(current.get("job_id") or "") == str(job_id) and str(current.get("state") or "") == "cancel_requested"


def request_cancel() -> dict:
    with _LOCK:
        current = load_status()
        state = str(current.get("state") or "idle")
        job_id = str(current.get("job_id") or "")
        if state not in {"running", "cancel_requested"}:
            return {"changed": False, "state": state}
        _CANCEL_EVENT.set()
        active_here = bool(_ACTIVE_JOB_ID and job_id and _ACTIVE_JOB_ID == job_id)
        if active_here:
            payload = {**current, "state": "cancel_requested", "stage": "Abbruch angefordert – aktueller API-Aufruf wird noch beendet"}
        else:
            payload = {**current, "state": "cancelled", "finished_at": _now_iso(), "stage": "Veralteter Jobstatus zurückgesetzt"}
        storage.save_job(payload)
        return {"changed": True, "state": payload["state"]}


def reset_status() -> None:
    global _ACTIVE_JOB_ID
    with _LOCK:
        _CANCEL_EVENT.set()
        _ACTIVE_JOB_ID = None
        storage.save_job({"state": "idle", "finished_at": _now_iso(), "stage": "Kommentarabruf-Status wurde zurückgesetzt."})


def run_fetch_job(job_id: str) -> None:
    global _ACTIVE_JOB_ID
    with _LOCK:
        _ACTIVE_JOB_ID = job_id
    current = _read_raw()
    started_at = current.get("started_at") or _now_iso()

    def progress(data: dict) -> None:
        latest = _read_raw()
        if str(latest.get("job_id") or "") != str(job_id):
            return
        storage.save_job({**latest, **data, "state": latest.get("state", "running"), "started_at": started_at})

    try:
        result = CommentMonitorService().fetch_all(
            should_cancel=lambda: _is_cancel_requested(job_id),
            progress_callback=progress,
        )
        latest = _read_raw()
        if str(latest.get("job_id") or "") != str(job_id):
            return
        if _is_cancel_requested(job_id):
            storage.save_job({**latest, "state": "cancelled", "finished_at": _now_iso(), "stage": "Kommentarabruf wurde abgebrochen."})
            return
        storage.save_job({
            "state": "success",
            "job_id": job_id,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "page_index": int(result.get("page_count", 0)),
            "page_count": int(result.get("page_count", 0)),
            "page_name": "",
            "stage": "Kommentarabruf abgeschlossen",
            "new_count": result.get("new_count", 0),
            "seen_count": result.get("seen_count", 0),
            "error_count": result.get("error_count", 0),
            "pages": result.get("pages", []),
            "error": "",
        })
    except CommentFetchCancelled:
        latest = _read_raw()
        if str(latest.get("job_id") or "") == str(job_id):
            storage.save_job({**latest, "state": "cancelled", "finished_at": _now_iso(), "stage": "Kommentarabruf wurde abgebrochen."})
    except Exception as error:
        latest = _read_raw()
        if str(latest.get("job_id") or "") == str(job_id):
            storage.save_job({
                **latest,
                "state": "error",
                "finished_at": _now_iso(),
                "error": str(error),
            })
    finally:
        with _LOCK:
            if _ACTIVE_JOB_ID == job_id:
                _ACTIVE_JOB_ID = None
            _CANCEL_EVENT.clear()
