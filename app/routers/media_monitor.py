from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.media_monitor.job import load_status, mark_started, run_fetch_job
from app.media_monitor.analysis import run_item_analysis
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

@router.get("/media-monitor/analysis/{item_id}", name="medienmonitor_analyse")
def medienmonitor_analyse(request: Request, item_id: str, started: int = 0):
    items = load_items()
    item = next((entry for entry in items if str(entry.get("id")) == str(item_id)), None)
    if item is None:
        return RedirectResponse(url="/media-monitor", status_code=303)
    item["published_display"] = _format_datetime(item.get("published_at"))
    item["analysis_updated_display"] = _format_datetime(item.get("analysis_updated_at")) if item.get("analysis_updated_at") else None
    cluster_id = str(item.get("trend_cluster_id") or "")
    related_items = []
    if cluster_id:
        for other in items:
            if str(other.get("id")) == str(item_id):
                continue
            if str(other.get("trend_cluster_id") or "") == cluster_id:
                related_items.append({
                    "source": other.get("source"),
                    "title": other.get("title"),
                    "url": other.get("url"),
                })
    return templates.TemplateResponse(
        request=request,
        name="media_analysis.html",
        context={
            "item": item,
            "related_items": related_items,
            "analysis_running": item.get("analysis_status") == "running",
            "analysis_done": item.get("analysis_status") == "done",
            "analysis_error": item.get("analysis_status") == "error",
            "started": bool(started),
        },
    )


@router.post("/media-monitor/analysis/{item_id}", name="medienmonitor_analyse_starten")
def medienmonitor_analyse_starten(item_id: str, background_tasks: BackgroundTasks):
    items = load_items()
    item = next((entry for entry in items if str(entry.get("id")) == str(item_id)), None)
    if item is None:
        return RedirectResponse(url="/media-monitor", status_code=303)
    if item.get("analysis_status") != "running":
        item["analysis_status"] = "running"
        item["analysis_error"] = ""
        from app.media_monitor.storage import save_items
        save_items(items)
        background_tasks.add_task(run_item_analysis, item_id)
    return RedirectResponse(url=f"/media-monitor/analysis/{item_id}?started=1", status_code=303)

