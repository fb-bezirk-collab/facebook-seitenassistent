from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR, UPLOADS_DIR
from app.services.post_service import PostService
from app.services.publication_service import PublicationService
from app.services.social_account_service import SocialAccountService


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

post_service = PostService()
publication_service = PublicationService()
account_service = SocialAccountService()


def _image_path_to_url(image_path: str) -> str | None:
    normalized = str(image_path).strip().replace("\\", "/")

    if not normalized:
        return None

    if normalized.startswith(("http://", "https://")):
        return normalized

    if normalized.startswith("/uploads/"):
        return normalized

    if normalized.startswith("uploads/"):
        return f"/{normalized}"

    path = Path(normalized)

    try:
        relative_path = path.resolve().relative_to(UPLOADS_DIR.resolve())
        return f"/uploads/{relative_path.as_posix()}"
    except ValueError:
        upload_marker = "uploads/"
        marker_position = normalized.find(upload_marker)

        if marker_position >= 0:
            return f"/{normalized[marker_position:]}"

        return None


def _create_image_urls(images: list[str]) -> list[str]:
    """Erzeugt für alle gespeicherten Bilder gültige Browser-URLs."""
    image_urls: list[str] = []

    for image_path in images:
        image_url = _image_path_to_url(image_path)

        if image_url:
            image_urls.append(image_url)

    return image_urls


@router.post("/drafts")
def entwurf_speichern(
    request: Request,
    title: str = Form(""),
    text: str = Form(""),
    images: list[str] = Form(default=[]),
    videos: list[str] = Form(default=[]),
    video_url: str = Form(""),
    page_id: str = Form(""),
    source_url: str = Form(""),
):
    if not text.strip() and not images and not videos and not video_url.strip():
        raise HTTPException(
            status_code=400,
            detail="Ein Entwurf benötigt Text, ein Bild oder einen Video-Link.",
        )

    draft = post_service.create_draft(
        title=title,
        text=text,
        images=images,
        videos=videos,
        video_url=video_url,
        page_id=page_id,
        source_url=source_url,
    )

    return RedirectResponse(
        url=(
            str(request.url_for("entwurf_bearbeiten", post_id=draft.id))
            + "?saved=1"
        ),
        status_code=303,
    )


@router.get("/drafts", name="entwuerfe_anzeigen")
def entwuerfe_anzeigen(request: Request, deleted: int = 0):
    drafts = post_service.list_posts(status="draft")

    return templates.TemplateResponse(
        request=request,
        name="drafts.html",
        context={
            "drafts": drafts,
            "deleted": bool(deleted),
            "publication_counts": {
                post.id: len(
                    publication_service.list_publications(post.id)
                )
                for post in drafts
            },
        },
    )


@router.get("/drafts/{post_id}", name="entwurf_bearbeiten")
def entwurf_bearbeiten(
    request: Request,
    post_id: str,
    saved: int = 0,
    planned: int = 0,
    published: int = 0,
    publish_error: str | None = None,
):
    draft = post_service.get_post(post_id)

    if not draft or draft.status != "draft":
        raise HTTPException(
            status_code=404,
            detail="Entwurf nicht gefunden.",
        )

    return templates.TemplateResponse(
        request=request,
        name="draft_edit.html",
        context={
            "draft": draft,
            "saved": bool(saved),
            "image_urls": _create_image_urls(draft.images),
            "planned": bool(planned),
            "published": bool(published),
            "publish_error": publish_error,
            "publications": publication_service.list_publications(post_id),
            "social_accounts": account_service.list_accounts(
                include_inactive=False
            ),
        },
    )


@router.post("/drafts/{post_id}")
def entwurf_aktualisieren(
    request: Request,
    post_id: str,
    title: str = Form(""),
    text: str = Form(""),
    images: list[str] = Form(default=[]),
    videos: list[str] = Form(default=[]),
    video_url: str = Form(""),
    page_id: str = Form(""),
    source_url: str = Form(""),
):
    draft = post_service.update_draft(
        post_id,
        title=title,
        text=text,
        images=images,
        videos=videos,
        video_url=video_url,
        page_id=page_id,
        source_url=source_url,
    )

    if not draft:
        raise HTTPException(
            status_code=404,
            detail="Entwurf nicht gefunden.",
        )

    return RedirectResponse(
        url=(
            str(request.url_for("entwurf_bearbeiten", post_id=post_id))
            + "?saved=1"
        ),
        status_code=303,
    )


@router.post("/drafts/{post_id}/delete")
def entwurf_loeschen(request: Request, post_id: str):
    publication_service.delete_for_post(post_id)

    if not post_service.delete_draft(post_id):
        raise HTTPException(
            status_code=404,
            detail="Entwurf nicht gefunden.",
        )

    return RedirectResponse(
        url=str(request.url_for("entwuerfe_anzeigen")) + "?deleted=1",
        status_code=303,
    )