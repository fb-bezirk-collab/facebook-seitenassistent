from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR
from app.media_monitor.service import MediaFetchCancelled, fetch_current_media

STATUS_FILE = DATA_DIR / "media_monitor_job.json"
_LOCK = threading.RLock()
_CANCEL_EVENT = threading.Event()
_ACTIVE_JOB_ID: str | None = None

# Ein frisch gestarteter BackgroundTask kann für wenige Sekunden noch nicht
# im Worker laufen. Erst danach darf ein persistierter "running"-Status ohne
# aktiven In-Memory-Job als veraltet angesehen werden.
STALE_GRACE_SECONDS = 90


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_status(payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(STATUS_FILE) + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATUS_FILE)


def _read_status_raw() -> dict[str, Any]:
    if not STATUS_FILE.exists():
        return {"state": "idle"}
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "idle"}
    return data if isinstance(data, dict) else {"state": "idle"}


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


def load_status() -> dict[str, Any]:
    """Lädt den persistenten Status und heilt veraltete Running-Zustände.

    Nach einem Railway-Restart ist der Python-Hintergrundjob weg, die JSON-Datei
    im Volume bleibt aber erhalten. Ein alter "running"-Status wird daher nach
    einer kurzen Schutzfrist automatisch als unterbrochen markiert.
    """
    global _ACTIVE_JOB_ID
    data = _read_status_raw()
    state = str(data.get("state") or "idle")
    job_id = str(data.get("job_id") or "")
    age = _age_seconds(data.get("started_at"))

    if state in {"running", "cancel_requested"}:
        with _LOCK:
            active_here = bool(_ACTIVE_JOB_ID and job_id and _ACTIVE_JOB_ID == job_id)
        if not active_here and (age is None or age > STALE_GRACE_SECONDS):
            if state == "cancel_requested":
                healed = {
                    **data,
                    "state": "cancelled",
                    "finished_at": _now_iso(),
                    "message": "Der Medienabruf wurde beendet.",
                }
            else:
                healed = {
                    **data,
                    "state": "error",
                    "finished_at": _now_iso(),
                    "error": (
                        "Der vorige Medienabruf wurde unterbrochen – vermutlich durch "
                        "einen Railway-Neustart oder einen abgebrochenen Worker. "
                        "Du kannst den Abruf jetzt neu starten."
                    ),
                }
            _write_status(healed)
            return healed

    return data


def mark_started() -> str | None:
    """Reserviert einen neuen Abruf und liefert dessen Job-ID.

    None bedeutet: Es läuft bereits ein Abruf in diesem Worker oder der
    persistierte Status ist noch aktiv.
    """
    global _ACTIVE_JOB_ID
    with _LOCK:
        current = load_status()
        if _ACTIVE_JOB_ID:
            return None
        if current.get("state") in {"running", "cancel_requested"}:
            return None

        job_id = uuid.uuid4().hex
        _CANCEL_EVENT.clear()
        _write_status({
            "state": "running",
            "job_id": job_id,
            "started_at": _now_iso(),
            "finished_at": None,
            "message": "Medien werden abgerufen und anschließend von der KI bewertet.",
            "progress_percent": 0,
            "progress_stage": "Medienabruf wird gestartet",
        })
        return job_id


def _is_cancel_requested(job_id: str) -> bool:
    if _CANCEL_EVENT.is_set():
        return True
    current = _read_status_raw()
    return (
        str(current.get("job_id") or "") == str(job_id)
        and str(current.get("state") or "") == "cancel_requested"
    )


def request_cancel() -> dict[str, Any]:
    """Fordert den Abbruch eines laufenden Medienjobs an.

    Ein gerade blockierender externer HTTP-Aufruf kann nicht mitten im Socket-
    Wait zwangsweise beendet werden. Der Job stoppt aber beim nächsten sicheren
    Prüfpunkt und beginnt keine weitere Quelle/KI-Stufe mehr.
    """
    global _ACTIVE_JOB_ID
    with _LOCK:
        current = load_status()
        state = str(current.get("state") or "idle")
        job_id = str(current.get("job_id") or "")

        if state not in {"running", "cancel_requested"}:
            return {"changed": False, "state": state, "message": "Es läuft kein Medienabruf."}

        _CANCEL_EVENT.set()
        active_here = bool(_ACTIVE_JOB_ID and job_id and _ACTIVE_JOB_ID == job_id)

        if active_here:
            payload = {
                **current,
                "state": "cancel_requested",
                "message": "Abbruch angefordert. Der aktuelle Schritt wird noch sauber beendet.",
            }
        else:
            # Persistierter Altstatus, aber kein laufender Job in diesem Prozess.
            payload = {
                **current,
                "state": "cancelled",
                "finished_at": _now_iso(),
                "message": "Der veraltete Medienabruf-Status wurde zurückgesetzt.",
            }
        _write_status(payload)
        return {"changed": True, "state": payload["state"], "message": payload.get("message", "")}


def reset_status() -> None:
    """Setzt ausschließlich den Jobstatus zurück; gespeicherte Medien bleiben erhalten."""
    global _ACTIVE_JOB_ID
    with _LOCK:
        _CANCEL_EVENT.set()
        _ACTIVE_JOB_ID = None
        _write_status({
            "state": "idle",
            "finished_at": _now_iso(),
            "message": "Medienabruf-Status wurde zurückgesetzt.",
        })


def run_fetch_job(job_id: str) -> None:
    """Wird nach der HTTP-Antwort als Hintergrundjob ausgeführt."""
    global _ACTIVE_JOB_ID
    with _LOCK:
        _ACTIVE_JOB_ID = job_id

    current = _read_status_raw()
    started_at = current.get("started_at") or _now_iso()

    def update_progress(percent: int, stage: str) -> None:
        latest = _read_status_raw()
        if str(latest.get("job_id") or "") != str(job_id):
            return
        if str(latest.get("state") or "") not in {"running", "cancel_requested"}:
            return
        stage_text = str(stage or "Medienabruf läuft")
        progress_phase = "other"
        progress_current = 0
        progress_total = 0
        progress_name = ""
        import re
        source_match = re.match(r"Quelle\s+(\d+)\s+von\s+(\d+):\s*(.+)", stage_text)
        ai_match = re.match(r"KI-Bewertung:\s*Paket\s+(\d+)\s+von\s+(\d+)", stage_text)
        if source_match:
            progress_phase = "sources"
            progress_current = int(source_match.group(1))
            progress_total = int(source_match.group(2))
            progress_name = source_match.group(3).strip()
        elif ai_match:
            progress_phase = "ai"
            progress_current = int(ai_match.group(1))
            progress_total = int(ai_match.group(2))
        _write_status({
            **latest,
            "progress_percent": max(0, min(99, int(percent))),
            "progress_stage": stage_text,
            "progress_phase": progress_phase,
            "progress_current": progress_current,
            "progress_total": progress_total,
            "progress_name": progress_name,
        })

    try:
        result = fetch_current_media(lambda: _is_cancel_requested(job_id), update_progress)

        # Falls zwischenzeitlich abgebrochen/resetet oder ein neuer Job gestartet
        # wurde, darf dieser alte Worker den Status nicht überschreiben.
        latest = _read_status_raw()
        if str(latest.get("job_id") or "") != str(job_id):
            return
        if _is_cancel_requested(job_id):
            _write_status({
                **latest,
                "state": "cancelled",
                "finished_at": _now_iso(),
                "message": "Der Medienabruf wurde abgebrochen.",
            })
            return

        _write_status({
            "state": "success",
            "job_id": job_id,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "new_count": int(result.get("new_count", 0)),
            "excluded_count": int(result.get("excluded_count", 0)),
            "rated_count": int(result.get("rated_count", 0)),
            "visible_count": int(result.get("visible_count", 0)),
            "trend_count": int(result.get("trend_count", 0)),
            "warning": str(result.get("rating_error", "") or ""),
            "source_results": result.get("source_results", []),
            "progress_percent": 100,
            "progress_stage": "Medienabruf abgeschlossen",
        })
    except MediaFetchCancelled:
        latest = _read_status_raw()
        if str(latest.get("job_id") or "") == str(job_id):
            _write_status({
                **latest,
                "state": "cancelled",
                "finished_at": _now_iso(),
                "message": "Der Medienabruf wurde abgebrochen.",
            })
    except Exception as exc:
        message = str(exc).strip() or "Unbekannter Fehler beim Medienabruf."
        print(f"Fehler im KI-Medienmonitor-Hintergrundjob: {exc}", flush=True)
        latest = _read_status_raw()
        if str(latest.get("job_id") or "") == str(job_id):
            _write_status({
                "state": "error",
                "job_id": job_id,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "error": message,
            })
    finally:
        with _LOCK:
            if _ACTIVE_JOB_ID == job_id:
                _ACTIVE_JOB_ID = None
            _CANCEL_EVENT.clear()
