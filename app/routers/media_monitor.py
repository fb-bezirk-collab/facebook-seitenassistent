from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
LOCAL_TIMEZONE = ZoneInfo("Europe/Vienna")


@router.get("/media-monitor", name="medienmonitor")
def medienmonitor(request: Request, fetched: int = 0):
    return templates.TemplateResponse(
        request=request,
        name="media_monitor.html",
        context={
            "items": [],
            "fetched": bool(fetched),
            "last_test_at": datetime.now(LOCAL_TIMEZONE).strftime("%d.%m.%Y, %H:%M Uhr")
            if fetched
            else None,
        },
    )


@router.post("/media-monitor/fetch", name="medienmonitor_abrufen")
def medienmonitor_abrufen():
    """Technischer Test-Endpunkt. Der echte Medienabruf folgt im nächsten Schritt."""
    return RedirectResponse(url="/media-monitor?fetched=1", status_code=303)
