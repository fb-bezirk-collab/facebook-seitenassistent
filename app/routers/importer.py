from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR, UPLOADS_DIR
from app.services.facebook_importer import FacebookImporter


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _image_path_to_url(image_path: str) -> str | None:
    """
    Wandelt einen internen Dateipfad in eine öffentliche Bild-URL um.

    Beispiel:
    /app/storage/uploads/facebook/2026-07-29/bild.jpg
    wird zu:
    /uploads/facebook/2026-07-29/bild.jpg
    """
    path = Path(image_path)

    try:
        relative_path = path.resolve().relative_to(UPLOADS_DIR.resolve())
        return f"/uploads/{relative_path.as_posix()}"
    except ValueError:
        normalized = str(image_path).replace("\\", "/").lstrip("/")

        # Rückwärtskompatibilität für ältere relative Pfade
        if normalized.startswith("uploads/"):
            return f"/{normalized}"

        return None


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
        if selected_type == "video":
            from app.models.facebook_post import FacebookPost

            cleaned_video_url = (video_url or facebook_url).strip()
            if not cleaned_video_url:
                raise ValueError("Bitte einen Reel- oder Videolink eingeben.")

            post = FacebookPost(
                text="",
                images=[],
                videos=[],
                video_url=cleaned_video_url,
                source_url=cleaned_video_url,
            )

            return templates.TemplateResponse(
                request=request,
                name="index.html",
                context={
                    "post": post,
                    "image_urls": [],
                    "error": None,
                    "facebook_url": cleaned_video_url,
                    "video_url": cleaned_video_url,
                    "import_type": selected_type,
                },
            )

        importer = FacebookImporter()
        post = importer.import_from_url(
            facebook_url,
            import_type=selected_type,
            video_url=video_url,
        )

        image_urls: list[str] = []

        for image_path in post.images:
            image_url = _image_path_to_url(image_path)
            if image_url:
                image_urls.append(image_url)

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "post": post,
                "image_urls": image_urls,
                "error": None,
                "facebook_url": facebook_url,
                "video_url": "",
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
