from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.services.post_service import PostService


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
post_service = PostService()


@router.post("/drafts")
def entwicklung_speichern(
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
        url=str(request.url_for("entwurf_bearbeiten", post_id=draft.id)) + "?saved=1",
        status_code=303,
    )


@router.get("/drafts", name="entwuerfe_anzeigen")
def entwuerfe_anzeigen(request: Request, deleted: int = 0):
    return templates.TemplateResponse(
        request=request,
        name="drafts.html",
        context={
            "drafts": post_service.list_posts(status="draft"),
            "deleted": bool(deleted),
        },
    )


@router.get("/drafts/{post_id}", name="entwurf_bearbeiten")
def entwurf_bearbeiten(request: Request, post_id: str, saved: int = 0):
    draft = post_service.get_post(post_id)
    if not draft or draft.status != "draft":
        raise HTTPException(status_code=404, detail="Entwurf nicht gefunden.")

    return templates.TemplateResponse(
        request=request,
        name="draft_edit.html",
        context={
            "draft": draft,
            "saved": bool(saved),
            "image_urls": ["/" + image for image in draft.images],
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
        raise HTTPException(status_code=404, detail="Entwurf nicht gefunden.")

    return RedirectResponse(
        url=str(request.url_for("entwurf_bearbeiten", post_id=post_id)) + "?saved=1",
        status_code=303,
    )


@router.post("/drafts/{post_id}/delete")
def entwurf_loeschen(request: Request, post_id: str):
    if not post_service.delete_draft(post_id):
        raise HTTPException(status_code=404, detail="Entwurf nicht gefunden.")

    return RedirectResponse(
        url=str(request.url_for("entwuerfe_anzeigen")) + "?deleted=1",
        status_code=303,
    )
