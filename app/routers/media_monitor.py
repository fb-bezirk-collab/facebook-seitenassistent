from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.media_monitor.job import load_status, mark_started, run_fetch_job
from app.media_monitor.storage import load_items


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
LOCAL_TIMEZONE = ZoneInfo("Europe/Vienna")


def _format_datetime(value: str | None) -> str:
    if not value:
        return "Zeit nicht angegeben"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(LOCAL_TIMEZONE).strftime("%d.%m.%Y, %H:%M Uhr")
    except (TypeError, ValueError):
        return "Zeit nicht angegeben"


@router.get("/media-monitor", name="medienmonitor")
def medienmonitor(request: Request, show_all: int = 0, started: int = 0, already_running: int = 0):
    all_items = load_items()
    items = all_items if show_all else [item for item in all_items if item.get("visibility") == "visible"]
    for item in items:
        item["published_display"] = _format_datetime(item.get("published_at"))
        item["fetched_display"] = _format_datetime(item.get("fetched_at"))

    job = load_status()
    state = str(job.get("state", "idle"))
    finished_at = _format_datetime(job.get("finished_at")) if job.get("finished_at") else None

    return templates.TemplateResponse(
        request=request,
        name="media_monitor.html",
        context={
            "items": items,
            "all_count": len(all_items),
            "show_all": bool(show_all),
            "job_running": state == "running",
            "job_success": state == "success",
            "job_error": state == "error",
            "job_started": bool(started),
            "already_running": bool(already_running),
            "new_count": max(0, int(job.get("new_count", 0) or 0)),
            "excluded_count": max(0, int(job.get("excluded_count", 0) or 0)),
            "rated_count": max(0, int(job.get("rated_count", 0) or 0)),
            "visible_count": max(0, int(job.get("visible_count", 0) or 0)),
            "trend_count": max(0, int(job.get("trend_count", 0) or 0)),
            "warning": str(job.get("warning", "") or ""),
            "error": str(job.get("error", "") or ""),
            "source_results": job.get("source_results", []) if isinstance(job.get("source_results"), list) else [],
            "last_fetch_at": finished_at,
        },
    )


@router.post("/media-monitor/fetch", name="medienmonitor_abrufen")
def medienmonitor_abrufen(background_tasks: BackgroundTasks):
    if not mark_started():
        return RedirectResponse(url="/media-monitor?already_running=1", status_code=303)
    background_tasks.add_task(run_fetch_job)
    return RedirectResponse(url="/media-monitor?started=1", status_code=303)
