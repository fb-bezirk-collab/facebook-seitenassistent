from __future__ import annotations

from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.comment_monitor.job import load_status as load_comment_job_status, mark_started, request_cancel as request_comment_cancel, reset_status as reset_comment_job_status, run_fetch_job
from app.comment_monitor.refresh_job import mark_refresh_started, run_refresh_job
from app.comment_monitor.ai import AI_CLASSIFICATION_VERSION
from app.comment_monitor.ai_job import mark_ai_started, run_ai_job
from app.comment_monitor.service import CommentMonitorService
from app.comment_monitor.storage import CommentStorage
from app.comment_monitor.users import build_user_profiles, get_user_profile, user_key_for_name
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
    archive: str = "",
    view_status: str = "new",
):
    all_comments = storage.load()
    all_comments.sort(key=lambda item: item.created_time or item.fetched_at, reverse=True)

    archive_mode = str(archive or "").strip().lower()
    if archive_mode not in {"all", "processed"}:
        archive_mode = ""

    # Eine echte Antwort der Seite lässt sich erkennen, wenn ein gespeicherter
    # Kind-Kommentar von der jeweiligen Facebook-Seite selbst stammt.
    replied_parent_ids = {
        item.parent_id
        for item in all_comments
        if item.parent_id
        and (
            (item.author_id and item.author_id == item.page_id)
            or (
                item.author_name
                and item.page_name
                and item.author_name.strip().casefold() == item.page_name.strip().casefold()
            )
        )
    }

    def is_page_reply(item) -> bool:
        return bool(
            item.parent_id
            and (
                (item.author_id and item.author_id == item.page_id)
                or (
                    item.author_name
                    and item.page_name
                    and item.author_name.strip().casefold() == item.page_name.strip().casefold()
                )
            )
        )

    def is_archived(item) -> bool:
        return (
            item.status in {"handled", "hidden", "deleted"}
            or item.comment_id in replied_parent_ids
            or is_page_reply(item)
        )

    def is_processed(item) -> bool:
        return item.status == "deleted" or item.comment_id in replied_parent_ids or is_page_reply(item)

    archived_comments = [item for item in all_comments if is_archived(item)]
    active_comments = [item for item in all_comments if not is_archived(item)]

    if archive_mode == "processed":
        comments = [item for item in archived_comments if is_processed(item)]
    elif archive_mode == "all":
        comments = archived_comments
    else:
        comments = active_comments

    rows = []
    for item in comments:
        row = item.to_dict()
        row["created_display"] = _format_datetime(item.created_time)
        row["post_preview"] = (item.post_message or "Beitrag ohne Text")[:180]
        row["ai_needs_update"] = item.ai_version != AI_CLASSIFICATION_VERSION
        row["user_key"] = user_key_for_name(item.author_name)
        row["moderation_recommended"] = item.ai_recommendation in {"Ausblenden prüfen", "Löschen prüfen"}
        row["reply_recommended"] = item.ai_recommendation == "Antworten"
        at = (item.attachment_type or "").casefold()
        if at == "sticker_or_media":
            row["attachment_label"] = "Sticker/Medienkommentar"
        elif "sticker" in at:
            row["attachment_label"] = "Sticker"
        elif "gif" in at or "animated" in at:
            row["attachment_label"] = "GIF"
        elif "video" in at:
            row["attachment_label"] = "Video"
        elif at == "link" and item.attachment_image_url:
            row["attachment_label"] = "Linkvorschau"
        elif item.attachment_image_url or "photo" in at or "image" in at:
            row["attachment_label"] = "Bild"
        elif item.attachment_type or item.attachment_url:
            row["attachment_label"] = "Medienanhang"
        else:
            row["attachment_label"] = ""
        rows.append(row)

    job = load_comment_job_status()
    state = str(job.get("state", "idle"))
    ai_job = storage.load_ai_job()
    ai_state = str(ai_job.get("state", "idle"))
    refresh_job = storage.load_refresh_job()
    refresh_state = str(refresh_job.get("state", "idle"))

    page_names = sorted({item.page_name for item in comments if item.page_name}, key=str.lower)
    user_profiles = build_user_profiles(all_comments)
    counts = {
        "all": len(all_comments),
        "new": sum(1 for item in all_comments if item.status == "new"),
        "handled": sum(1 for item in all_comments if item.status == "handled"),
        "hidden": sum(1 for item in all_comments if item.status == "hidden"),
        "deleted": sum(1 for item in all_comments if item.status == "deleted"),
        "questions": sum(1 for item in all_comments if item.ai_category == "Frage"),
        "critical": sum(1 for item in all_comments if item.ai_category in {"Meinung/Kritik", "Provokation", "Beleidigung", "Drohung/Gewalt"}),
        "moderation": sum(1 for item in all_comments if item.ai_recommendation in {"Ausblenden prüfen", "Löschen prüfen"}),
        "unanalyzed": sum(1 for item in all_comments if item.status != "deleted" and item.ai_version != AI_CLASSIFICATION_VERSION and ((item.message or "").strip() or item.attachment_type or item.attachment_url or item.attachment_image_url)),
        "ai_errors": sum(1 for item in all_comments if item.status != "deleted" and bool(item.ai_error)),
        "media_comments": sum(1 for item in all_comments if item.attachment_type or item.attachment_url or item.attachment_image_url),
        "reply_recommended": sum(1 for item in all_comments if item.ai_recommendation == "Antworten"),
        "spam": sum(1 for item in all_comments if item.ai_category == "Spam"),
        "off_topic": sum(1 for item in all_comments if item.ai_category == "Off-Topic"),
        "users": len(user_profiles),
        "repeat_users": sum(1 for profile in user_profiles if profile.get("repeated_comment_count", 0) >= 3 or profile.get("moderation_count", 0) >= 3),
    }

    archive_count = len(archived_comments)
    archive_processed_count = sum(1 for item in archived_comments if is_processed(item))
    selected_status = (
        "archive:processed" if archive_mode == "processed"
        else "archive:all" if archive_mode == "all"
        else view_status if view_status in {"new", "handled", "hidden", "deleted", "all"} else "new"
    )

    first_page_error = next(
        (str(page.get("error", "")) for page in job.get("pages", []) if page.get("error")),
        "",
    )

    return templates.TemplateResponse(
        request=request,
        name="comments.html",
        context={
            "comments": rows,
            "page_names": page_names,
            "user_profiles": user_profiles[:25],
            "counts": counts,
            "job_running": state == "running",
            "job_success": state == "success",
            "job_error": state == "error",
            "job_cancelling": state == "cancel_requested",
            "job_cancelled": state == "cancelled",
            "started": bool(started),
            "already_running": bool(already_running),
            "job": job,
            "ai_job": ai_job,
            "ai_job_running": ai_state == "running",
            "ai_job_success": ai_state in {"success", "success_with_errors"},
            "ai_job_partial": ai_state == "success_with_errors",
            "ai_job_error": ai_state == "error",
            "refresh_job": refresh_job,
            "refresh_job_running": refresh_state == "running",
            "refresh_job_success": refresh_state in {"success", "success_with_errors"},
            "refresh_job_partial": refresh_state == "success_with_errors",
            "refresh_job_error": refresh_state == "error",
            "any_reply_running": any(item.reply_status == "running" for item in all_comments),
            "first_page_error": first_page_error,
            "last_fetch_display": _format_datetime(job.get("finished_at")) if job.get("finished_at") else None,
            "action": action or "",
            "action_error": error or "",
            "archive_mode": archive_mode,
            "archive_count": archive_count,
            "archive_processed_count": archive_processed_count,
            "selected_status": selected_status,
        },
    )


@router.post("/comments/fetch", name="kommentare_abrufen")
def kommentare_abrufen(background_tasks: BackgroundTasks):
    job_id = mark_started()
    if not job_id:
        return RedirectResponse(url="/comments?already_running=1", status_code=303)
    background_tasks.add_task(run_fetch_job, job_id)
    return RedirectResponse(url="/comments?started=1", status_code=303)


@router.post("/comments/fetch/cancel", name="kommentare_abruf_abbrechen")
def kommentare_abruf_abbrechen():
    request_comment_cancel()
    return RedirectResponse(url="/comments?action=fetch_cancel_requested", status_code=303)


@router.post("/comments/fetch/reset", name="kommentare_abruf_status_reset")
def kommentare_abruf_status_reset():
    reset_comment_job_status()
    return RedirectResponse(url="/comments?action=fetch_reset", status_code=303)


@router.post("/comments/refresh-existing", name="kommentare_bestehende_aktualisieren")
def kommentare_bestehende_aktualisieren(background_tasks: BackgroundTasks):
    if not mark_refresh_started():
        return RedirectResponse(url="/comments?already_running=1", status_code=303)
    background_tasks.add_task(run_refresh_job)
    return RedirectResponse(url="/comments?action=refresh_started", status_code=303)


@router.post("/comments/analyze", name="kommentare_analysieren")
def kommentare_analysieren(background_tasks: BackgroundTasks):
    if not mark_ai_started("all"):
        return RedirectResponse(url="/comments?already_running=1", status_code=303)
    background_tasks.add_task(run_ai_job, "all")
    return RedirectResponse(url="/comments?action=ai_started", status_code=303)



@router.post("/comments/analyze-errors", name="kommentare_analysefehler_wiederholen")
def kommentare_analysefehler_wiederholen(background_tasks: BackgroundTasks):
    if not mark_ai_started("errors"):
        return RedirectResponse(url="/comments?already_running=1", status_code=303)
    background_tasks.add_task(run_ai_job, "errors")
    return RedirectResponse(url="/comments?action=ai_errors_started", status_code=303)

def _run_reply_suggestion(comment_id: str) -> None:
    service.generate_reply_suggestion(comment_id)


@router.post("/comments/{comment_id}/suggest-reply", name="kommentar_antwort_vorschlagen")
def kommentar_antwort_vorschlagen(comment_id: str, background_tasks: BackgroundTasks):
    comment = storage.get(comment_id)
    if comment is None:
        return RedirectResponse(url="/comments?error=" + quote("Der Kommentar wurde nicht gefunden."), status_code=303)
    if comment.reply_status != "running":
        comment.reply_status = "running"
        comment.reply_error = ""
        storage.update(comment)
        background_tasks.add_task(_run_reply_suggestion, comment_id)
    return RedirectResponse(url="/comments?action=reply_started", status_code=303)


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


@router.get("/comments/users/{user_key}", name="kommentar_benutzerprofil")
def kommentar_benutzerprofil(request: Request, user_key: str, action: str | None = None, error: str | None = None):
    comments = storage.load()
    profile = get_user_profile(comments, user_key)
    if profile is None:
        return RedirectResponse(url="/comments?error=" + quote("Das Benutzerprofil wurde nicht gefunden."), status_code=303)
    rows = []
    for item in profile["comments"]:
        row = item.to_dict()
        row["created_display"] = _format_datetime(item.created_time)
        row["post_preview"] = (item.post_message or "Beitrag ohne Text")[:220]
        rows.append(row)
    profile = dict(profile)
    profile["comments"] = rows
    return templates.TemplateResponse(
        request=request,
        name="comment_user.html",
        context={"profile": profile, "action": action or "", "action_error": error or ""},
    )


@router.post("/comments/users/{user_key}/watch", name="kommentar_benutzer_beobachten")
def kommentar_benutzer_beobachten(user_key: str):
    try:
        service.set_user_watchlist(user_key, True)
        return RedirectResponse(url=f"/comments/users/{user_key}?action=watch", status_code=303)
    except FacebookApiError as error:
        return RedirectResponse(url=f"/comments/users/{user_key}?error=" + quote(str(error)), status_code=303)


@router.post("/comments/users/{user_key}/unwatch", name="kommentar_benutzer_nicht_beobachten")
def kommentar_benutzer_nicht_beobachten(user_key: str):
    try:
        service.set_user_watchlist(user_key, False)
        return RedirectResponse(url=f"/comments/users/{user_key}?action=unwatch", status_code=303)
    except FacebookApiError as error:
        return RedirectResponse(url=f"/comments/users/{user_key}?error=" + quote(str(error)), status_code=303)


@router.post("/comments/users/{user_key}/block-all-pages", name="kommentar_benutzer_sperren")
def kommentar_benutzer_sperren(user_key: str):
    try:
        result = service.set_user_blocked_on_all_pages(user_key, True)
        return RedirectResponse(
            url=(f"/comments/users/{user_key}?action=blocked_{result['success_count']}_"
                 f"{result['pending_count']}_{result['error_count']}"),
            status_code=303,
        )
    except FacebookApiError as error:
        return RedirectResponse(url=f"/comments/users/{user_key}?error=" + quote(str(error)), status_code=303)


@router.post("/comments/users/{user_key}/unblock-all-pages", name="kommentar_benutzer_entsperren")
def kommentar_benutzer_entsperren(user_key: str):
    try:
        result = service.set_user_blocked_on_all_pages(user_key, False)
        return RedirectResponse(
            url=f"/comments/users/{user_key}?action=unblocked_{result['success_count']}_{result['error_count']}",
            status_code=303,
        )
    except FacebookApiError as error:
        return RedirectResponse(url=f"/comments/users/{user_key}?error=" + quote(str(error)), status_code=303)
