from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from app.config import UPLOADS_DIR
from app.services.post_service import PostService


router = APIRouter()
post_service = PostService()

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


def _safe_suffix(
    filename: str,
    content_type: str,
) -> str:
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


async def _save_upload(
    upload: UploadFile,
) -> str:
    content_type = (
        upload.content_type or ""
    ).lower().strip()

    if (
        content_type not in ALLOWED_IMAGE_TYPES
        and content_type not in ALLOWED_VIDEO_TYPES
    ):
        raise ValueError(
            "Nicht unterstütztes Dateiformat: "
            f"{upload.filename or 'unbekannte Datei'}"
        )

    content = await upload.read()

    if not content:
        raise ValueError(
            f"Die Datei {upload.filename or ''} ist leer."
        )

    if len(content) > MAX_FILE_SIZE:
        raise ValueError(
            f"Die Datei {upload.filename or ''} "
            "ist größer als 150 MB."
        )

    target_directory = UPLOADS_DIR / "manual"
    target_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    suffix = _safe_suffix(
        upload.filename or "",
        content_type,
    )

    target_path = (
        target_directory
        / f"{uuid4().hex}{suffix}"
    )

    target_path.write_bytes(content)

    return target_path.relative_to(
        UPLOADS_DIR.parent
    ).as_posix()


@router.post("/manual-upload")
async def manueller_medienimport(
    request: Request,
    title: str = Form(""),
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
                "Bitte mindestens ein Bild "
                "oder Video auswählen."
            )

        images = [
            path
            for path in saved_files
            if Path(path).suffix.lower()
            in {
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
            }
        ]

        videos = [
            path
            for path in saved_files
            if Path(path).suffix.lower()
            in {
                ".mp4",
                ".mov",
                ".webm",
            }
        ]

        draft = post_service.create_draft(
            title=title,
            text=text.strip(),
            text_variants=[],
            images=images,
            videos=videos,
            video_url="",
            page_id="",
            source_url=source_url.strip(),
        )

        return RedirectResponse(
            url=(
                str(
                    request.url_for(
                        "entwurf_bearbeiten",
                        post_id=draft.id,
                    )
                )
                + "?saved=1"
            ),
            status_code=303,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@router.post("/own-post")
async def eigenen_beitrag_erstellen(
    request: Request,
    title: str = Form(""),
    text: str = Form(""),
    photo: UploadFile | None = File(default=None),
):
    """Erstellt einen eigenen Beitrag ohne Import; optional mit einem Foto."""
    clean_text = text.strip()
    images: list[str] = []

    try:
        if photo is not None and photo.filename:
            saved_path = await _save_upload(photo)
            if Path(saved_path).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                raise ValueError("Bitte als Foto JPG, PNG oder WebP auswählen.")
            images.append(saved_path)

        if not clean_text and not images:
            raise ValueError("Bitte einen Beitragstext eingeben oder ein Foto auswählen.")

        draft = post_service.create_draft(
            title=title,
            text=clean_text,
            text_variants=[],
            images=images,
            videos=[],
            video_url="",
            page_id="",
            source_url="",
        )
        return RedirectResponse(
            url=str(request.url_for("entwurf_bearbeiten", post_id=draft.id)) + "?saved=1",
            status_code=303,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
