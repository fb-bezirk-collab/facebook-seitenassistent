from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.services.post_service import PostService
from app.media_monitor.job import load_status, mark_started, run_fetch_job
from app.media_monitor.analysis import run_item_analysis
from app.media_monitor.storage import load_items, save_items


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
LOCAL_TIMEZONE = ZoneInfo("Europe/Vienna")
post_service = PostService()


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
def medienmonitor_analyse(request: Request, item_id: str, started: int = 0, draft_error: int = 0):
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
            "draft_error": bool(draft_error),
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



def _append_hashtags(text: str, hashtags: list[str]) -> str:
    clean = text.strip()
    tags = []
    for raw in hashtags if isinstance(hashtags, list) else []:
        tag = str(raw).strip()
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = "#" + tag.lstrip("#")
        if tag.lower() not in clean.lower() and tag not in tags:
            tags.append(tag)
    if not tags:
        return clean
    return clean + "\n\n" + " ".join(tags)


def _draft_variants(editorial: dict) -> list[dict[str, str]]:
    values = editorial.get("facebook_variants", {}) if isinstance(editorial, dict) else {}
    if not isinstance(values, dict):
        return []
    labels = (("sachlich", "Sachlich"), ("pointiert", "Pointiert"), ("emotional", "Emotional"), ("kampagne", "Kampagnenstil"))
    result = []
    for key, label in labels:
        value = str(values.get(key) or (values.get("mobil") if key == "kampagne" else "")).strip()
        if value:
            result.append({"title": label, "text": value})
    return result


@router.post("/media-monitor/analysis/{item_id}/draft", name="medienmonitor_entwurf_erstellen")
def medienmonitor_entwurf_erstellen(
    request: Request,
    item_id: str,
    headline_choice: str = Form("pointiert"),
    facebook_choice: str = Form("pointiert"),
    force_new: int = Form(0),
):
    items = load_items()
    item = next((entry for entry in items if str(entry.get("id")) == str(item_id)), None)
    if item is None:
        return RedirectResponse(url="/media-monitor", status_code=303)

    existing_draft_id = str(item.get("draft_id") or "").strip()
    if existing_draft_id and not force_new:
        existing = post_service.get_post(existing_draft_id)
        if existing is not None:
            return RedirectResponse(
                url=str(request.url_for("entwurf_bearbeiten", post_id=existing_draft_id)) + "?media_existing=1",
                status_code=303,
            )

    editorial = item.get("editorial") if isinstance(item.get("editorial"), dict) else {}
    headlines = editorial.get("headlines") if isinstance(editorial.get("headlines"), dict) else {}
    facebook = editorial.get("facebook_variants") if isinstance(editorial.get("facebook_variants"), dict) else {}

    valid_headlines = {"sachlich", "pointiert", "emotional", "kurz"}
    valid_facebook = {"sachlich", "pointiert", "emotional", "kampagne"}
    if headline_choice not in valid_headlines:
        headline_choice = "pointiert"
    if facebook_choice not in valid_facebook:
        facebook_choice = "pointiert"

    title = str(headlines.get(headline_choice) or item.get("title") or "Medienmonitor-Entwurf").strip()
    fb_text = str(facebook.get(facebook_choice) or (facebook.get("mobil") if facebook_choice == "kampagne" else "") or editorial.get("political_angle") or item.get("ai_summary") or "").strip()
    hashtags = editorial.get("hashtags") if isinstance(editorial.get("hashtags"), list) else []
    text = _append_hashtags(fb_text, hashtags)

    if not text:
        return RedirectResponse(url=f"/media-monitor/analysis/{item_id}?draft_error=1", status_code=303)

    variants = []
    for variant in _draft_variants(editorial):
        variants.append({
            "title": variant["title"],
            "text": _append_hashtags(variant["text"], hashtags),
        })

    graphic = editorial.get("graphic") if isinstance(editorial.get("graphic"), dict) else {}
    meta = {
        "origin": "media_monitor",
        "media_item_id": str(item.get("id") or ""),
        "source": str(item.get("source") or ""),
        "original_title": str(item.get("title") or ""),
        "published_at": item.get("published_at"),
        "categories": item.get("categories") if isinstance(item.get("categories"), list) else [],
        "region": str(item.get("region") or ""),
        "priority": str(editorial.get("priority") or ""),
        "priority_reason": str(editorial.get("priority_reason") or ""),
        "graphic": graphic,
        "trend_level": str(item.get("trend_level") or ""),
        "trend_source_count": int(item.get("trend_source_count") or 0),
        "headline_choice": headline_choice,
        "facebook_choice": facebook_choice,
    }

    draft = post_service.create_draft(
        title=title,
        text=text,
        text_variants=variants,
        images=[],
        videos=[],
        source_url=str(item.get("url") or ""),
        source_type="media_monitor",
        source_name=str(item.get("source") or ""),
        source_item_id=str(item.get("id") or ""),
        source_meta=meta,
    )

    item["created_post"] = True
    item["draft_id"] = draft.id
    item["draft_created_at"] = datetime.now(tz=LOCAL_TIMEZONE).isoformat()
    item["workflow_status"] = "draft_created"
    save_items(items)

    return RedirectResponse(
        url=str(request.url_for("entwurf_bearbeiten", post_id=draft.id)) + "?media_created=1",
        status_code=303,
    )
