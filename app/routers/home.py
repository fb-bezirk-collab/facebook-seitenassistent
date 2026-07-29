from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", name="startseite")
def startseite(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "post": None,
            "image_urls": [],
            "error": None,
            "facebook_url": "",
            "video_url": "",
            "import_type": "image",
        },
    )
