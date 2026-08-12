from __future__ import annotations

from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.comment_monitor.job import mark_started, run_fetch_job
from app.comment_monitor.service import CommentMonitorService
from app.comment_monitor.storage import CommentStorage
from app.config import TEMPLATES_DIR
from app.services.facebook_api import FacebookApiError


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
storage = CommentStorage()
service = CommentMonitorService()
LOCAL_TIMEZONE = ZoneInfo("Europe/Vienna")


def _format_datetime(value: str | None) -> str:
    if not value:
        return "Zeit nicht angegeben"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(LOCAL_TIMEZONE).strftime("%d.%m.%Y, %H:%M Uhr")
    except (TypeError, ValueError):
        return "Zeit nicht angegeben"


@router.get("/comments", name="kommentar_monitor")
def kommentar_monitor(
    request: Request,
    started: int = 0,
    already_running: int = 0,
    action: str | None = None,
    error: str | None = None,
):
    comments = storage.load()
    comments.sort(key=lambda item: item.created_time or item.fetched_at, reverse=True)

    rows = []
    for item in comments:
        row = item.to_dict()
        row["created_display"] = _format_datetime(item.created_time)
        row["post_preview"] = (item.post_message or "Beitrag ohne Text")[:180]
        rows.append(row)

    job = storage.load_job()
    state = str(job.get("state", "idle"))

    page_names = sorted({item.page_name for item in comments if item.page_name}, key=str.lower)
    counts = {
        "all": len(comments),
        "new": sum(1 for item in comments if item.status == "new"),
        "handled": sum(1 for item in comments if item.status == "handled"),
        "hidden": sum(1 for item in comments if item.status == "hidden"),
        "deleted": sum(1 for item in comments if item.status == "deleted"),
    }

    return templates.TemplateResponse(
        request=request,
        name="comments.html",
        context={
            "comments": rows,
            "page_names": page_names,
            "counts": counts,
            "job_running": state == "running",
            "job_success": state == "success",
            "job_error": state == "error",
            "started": bool(started),
            "already_running": bool(already_running),
            "job": job,
            "last_fetch_display": _format_datetime(job.get("finished_at")) if job.get("finished_at") else None,
            "action": action or "",
            "action_error": error or "",
        },
    )


@router.post("/comments/fetch", name="kommentare_abrufen")
def kommentare_abrufen(background_tasks: BackgroundTasks):
    if not mark_started():
        return RedirectResponse(url="/comments?already_running=1", status_code=303)
    background_tasks.add_task(run_fetch_job)
    return RedirectResponse(url="/comments?started=1", status_code=303)


@router.post("/comments/{comment_id}/hide", name="kommentar_ausblenden")
def kommentar_ausblenden(comment_id: str):
    try:
        service.set_hidden(comment_id, True)
        return RedirectResponse(url="/comments?action=hidden", status_code=303)
    except FacebookApiError as error:
        return RedirectResponse(url="/comments?error=" + quote(str(error)), status_code=303)


@router.post("/comments/{comment_id}/unhide", name="kommentar_einblenden")
def kommentar_einblenden(comment_id: str):
    try:
        service.set_hidden(comment_id, False)
        return RedirectResponse(url="/comments?action=unhidden", status_code=303)
    except FacebookApiError as error:
        return RedirectResponse(url="/comments?error=" + quote(str(error)), status_code=303)


@router.post("/comments/{comment_id}/delete", name="kommentar_loeschen")
def kommentar_loeschen(comment_id: str):
    try:
        service.delete(comment_id)
        return RedirectResponse(url="/comments?action=deleted", status_code=303)
    except FacebookApiError as error:
        return RedirectResponse(url="/comments?error=" + quote(str(error)), status_code=303)


@router.post("/comments/{comment_id}/handled", name="kommentar_erledigt")
def kommentar_erledigt(comment_id: str):
    try:
        service.set_handled(comment_id, True)
        return RedirectResponse(url="/comments?action=handled", status_code=303)
    except FacebookApiError as error:
        return RedirectResponse(url="/comments?error=" + quote(str(error)), status_code=303)


@router.post("/comments/{comment_id}/reopen", name="kommentar_wieder_offen")
def kommentar_wieder_offen(comment_id: str):
    try:
        service.set_handled(comment_id, False)
        return RedirectResponse(url="/comments?action=reopened", status_code=303)
    except FacebookApiError as error:
        return RedirectResponse(url="/comments?error=" + quote(str(error)), status_code=303)
