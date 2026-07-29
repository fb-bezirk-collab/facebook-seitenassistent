from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.services.facebook_importer import FacebookImporter


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/import", include_in_schema=False)
def import_aufruf_weiterleiten():
    return RedirectResponse(url="/", status_code=303)


@router.post("/import")
def beitrag_importieren(
    request: Request,
    facebook_url: str = Form(...),
    import_type: str = Form("image"),
    video_url: str = Form(""),
):
    selected_type = "video" if import_type == "video" else "image"

    try:
        importer = FacebookImporter()
        post = importer.import_from_url(
            facebook_url,
            import_type=selected_type,
            video_url=video_url,
        )

        image_urls = [
            "/" + image_path.replace("\\", "/")
            for image_path in post.images
        ]

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "post": post,
                "image_urls": image_urls,
                "error": None,
                "facebook_url": facebook_url,
                "video_url": video_url,
                "import_type": selected_type,
            },
        )

    except Exception as error:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "post": None,
                "image_urls": [],
                "error": str(error),
                "facebook_url": facebook_url,
                "video_url": video_url,
                "import_type": selected_type,
            },
            status_code=400,
        )
