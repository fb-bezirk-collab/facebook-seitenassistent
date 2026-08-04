from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR, UPLOADS_DIR
from app.models.facebook_post import FacebookPost


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
}

MAX_FILE_SIZE = 150 * 1024 * 1024


def _safe_suffix(filename: str, content_type: str) -> str:
    suffix = Path(filename or "").suffix.lower()

    if suffix:
        return suffix

    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/webm": ".webm",
    }

    return mapping.get(content_type, "")


async def _save_upload(upload: UploadFile) -> str:
    content_type = (upload.content_type or "").lower().strip()

    if (
        content_type not in ALLOWED_IMAGE_TYPES
        and content_type not in ALLOWED_VIDEO_TYPES
    ):
        raise ValueError(
            f"Nicht unterstütztes Dateiformat: "
            f"{upload.filename or 'unbekannte Datei'}"
        )

    content = await upload.read()

    if not content:
        raise ValueError(
            f"Die Datei {upload.filename or ''} ist leer."
        )

    if len(content) > MAX_FILE_SIZE:
        raise ValueError(
            f"Die Datei {upload.filename or ''} ist größer als 150 MB."
        )

    target_directory = UPLOADS_DIR / "manual"
    target_directory.mkdir(parents=True, exist_ok=True)

    suffix = _safe_suffix(
        upload.filename or "",
        content_type,
    )

    target_path = target_directory / f"{uuid4().hex}{suffix}"
    target_path.write_bytes(content)

    return target_path.relative_to(
        UPLOADS_DIR.parent
    ).as_posix()


@router.post("/manual-upload")
async def manueller_medienimport(
    request: Request,
    text: str = Form(""),
    source_url: str = Form(""),
    media_files: list[UploadFile] = File(default=[]),
):
    try:
        saved_files: list[str] = []

        for upload in media_files:
            if not upload.filename:
                continue

            saved_files.append(
                await _save_upload(upload)
            )

        if not saved_files:
            raise ValueError(
                "Bitte mindestens ein Bild oder Video auswählen."
            )

        images = [
            path
            for path in saved_files
            if Path(path).suffix.lower()
            in {".jpg", ".jpeg", ".png", ".webp"}
        ]

        videos = [
            path
            for path in saved_files
            if Path(path).suffix.lower()
            in {".mp4", ".mov", ".webm"}
        ]

        post = FacebookPost(
            text=text.strip(),
            images=images,
            videos=videos,
            video_url="",
            source_url=source_url.strip(),
        )

        image_urls = [
            "/" + image_path.replace("\\", "/")
            for image_path in images
        ]

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "post": post,
                "image_urls": image_urls,
                "error": None,
                "facebook_url": "",
                "video_url": "",
                "import_type": "manual",
                "source_mode": "manual",
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
                "facebook_url": "",
                "video_url": "",
                "import_type": "manual",
                "source_mode": "manual",
            },
            status_code=400,
        )
