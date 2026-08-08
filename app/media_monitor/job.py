from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR
from app.media_monitor.service import fetch_current_media

STATUS_FILE = DATA_DIR / "media_monitor_job.json"
_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_status(payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(STATUS_FILE) + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATUS_FILE)


def load_status() -> dict[str, Any]:
    if not STATUS_FILE.exists():
        return {"state": "idle"}
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "idle"}
    return data if isinstance(data, dict) else {"state": "idle"}


def mark_started() -> bool:
    """Reserviert einen neuen Abruf. False bedeutet: Ein Abruf läuft bereits."""
    with _LOCK:
        current = load_status()
        if current.get("state") == "running":
            return False
        _write_status({
            "state": "running",
            "started_at": _now_iso(),
            "finished_at": None,
            "message": "Medien werden abgerufen und anschließend von der KI bewertet.",
        })
        return True


def run_fetch_job() -> None:
    """Wird nach der HTTP-Antwort als Hintergrundjob ausgeführt."""
    started_at = load_status().get("started_at") or _now_iso()
    try:
        result = fetch_current_media()
        _write_status({
            "state": "success",
            "started_at": started_at,
            "finished_at": _now_iso(),
            "new_count": int(result.get("new_count", 0)),
            "excluded_count": int(result.get("excluded_count", 0)),
            "rated_count": int(result.get("rated_count", 0)),
            "visible_count": int(result.get("visible_count", 0)),
            "warning": str(result.get("rating_error", "") or ""),
            "source_results": result.get("source_results", []),
        })
    except Exception as exc:
        message = str(exc).strip() or "Unbekannter Fehler beim Medienabruf."
        print(f"Fehler im KI-Medienmonitor-Hintergrundjob: {exc}", flush=True)
        _write_status({
            "state": "error",
            "started_at": started_at,
            "finished_at": _now_iso(),
            "error": message,
        })
