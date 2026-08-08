from __future__ import annotations

from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.media_monitor.service import fetch_current_media
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
def medienmonitor(request: Request, fetched: int = 0, new: int = 0, excluded: int = 0, rated: int = 0, visible: int = 0, warning: str = "", error: str = "", show_all: int = 0):
    all_items = load_items()
    items = all_items if show_all else [item for item in all_items if item.get("visibility") == "visible"]
    for item in items:
        item["published_display"] = _format_datetime(item.get("published_at"))
        item["fetched_display"] = _format_datetime(item.get("fetched_at"))
    return templates.TemplateResponse(
        request=request,
        name="media_monitor.html",
        context={
            "items": items, "all_count": len(all_items), "show_all": bool(show_all),
            "fetched": bool(fetched), "new_count": max(0, new), "excluded_count": max(0, excluded),
            "rated_count": max(0, rated), "visible_count": max(0, visible),
            "warning": warning, "error": error,
            "last_fetch_at": datetime.now(LOCAL_TIMEZONE).strftime("%d.%m.%Y, %H:%M Uhr") if fetched or error else None,
        },
    )


@router.post("/media-monitor/fetch", name="medienmonitor_abrufen")
def medienmonitor_abrufen():
    try:
        result = fetch_current_media()
    except Exception as exc:
        message = str(exc).strip() or "Unbekannter Fehler beim Krone-Abruf."
        print(f"Fehler im KI-Medienmonitor: {exc}", flush=True)
        return RedirectResponse(url="/media-monitor?error=" + quote(message, safe=""), status_code=303)

    params = (
        f"fetched=1&new={result['new_count']}&excluded={result['excluded_count']}"
        f"&rated={result['rated_count']}&visible={result['visible_count']}"
    )
    if result["rating_error"]:
        params += "&warning=" + quote(result["rating_error"], safe="")
    return RedirectResponse(url="/media-monitor?" + params, status_code=303)
