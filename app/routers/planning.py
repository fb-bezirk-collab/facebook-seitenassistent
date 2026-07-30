from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.services.post_service import PostService
from app.services.publication_service import PublicationService
from app.services.social_account_service import SocialAccountService

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
post_service = PostService()
publication_service = PublicationService()
account_service = SocialAccountService()


@router.get("/planning", name="veroeffentlichungsplanung")
def planning(
    request: Request,
    saved: int = 0,
    deleted: int = 0,
    published: int = 0,
    publish_error: str | None = None,
):
    publications = publication_service.list_publications()
    posts = {post.id: post for post in post_service.list_posts()}
    grouped = defaultdict(list)
    for publication in publications:
        grouped[publication.publish_at[:10]].append(publication)
    return templates.TemplateResponse(
        request=request,
        name="planning.html",
        context={
            "publications": publications,
            "posts": posts,
            "grouped": dict(grouped),
            "saved": bool(saved),
            "deleted": bool(deleted),
            "published": bool(published),
            "publish_error": publish_error,
            "now": datetime.now().isoformat(timespec="minutes"),
        },
    )


@router.post("/drafts/{post_id}/publications")
def publication_create(
    request: Request,
    post_id: str,
    account_ids: list[str] = Form(default=[]),
    publish_at: str = Form(...),
):
    post = post_service.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Beitrag nicht gefunden.")
    if not account_ids:
        raise HTTPException(status_code=400, detail="Bitte mindestens eine Facebook-Seite auswählen.")

    accounts = []
    invalid_accounts = []
    for account_id in dict.fromkeys(account_ids):
        account = account_service.get(account_id)
        if not account or not account.active:
            invalid_accounts.append(account_id)
            continue
        accounts.append(account)

    if invalid_accounts:
        raise HTTPException(status_code=400, detail="Mindestens eine ausgewählte Seite ist nicht mehr verfügbar.")

    try:
        created = publication_service.create_many(
            post_id=post_id,
            accounts=accounts,
            publish_at=publish_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(
        url=(
            str(request.url_for("entwurf_bearbeiten", post_id=post_id))
            + f"?planned=1&planned_count={len(created)}"
        ),
        status_code=303,
    )


@router.post("/publications/{publication_id}")
def publication_update(
    request: Request,
    publication_id: str,
    publish_at: str = Form(...),
    status: str = Form("planned"),
):
    publication = publication_service.get(publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Planung nicht gefunden.")
    try:
        publication_service.update(publication_id, publish_at=publish_at, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        url=str(request.url_for("entwurf_bearbeiten", post_id=publication.post_id)) + "?planned=1",
        status_code=303,
    )


@router.post("/publications/{publication_id}/delete")
def publication_delete(request: Request, publication_id: str):
    publication = publication_service.get(publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Planung nicht gefunden.")
    publication_service.delete(publication_id)
    referer = request.headers.get("referer", "")
    if "/planning" in referer:
        url = str(request.url_for("veroeffentlichungsplanung")) + "?deleted=1"
    else:
        url = str(request.url_for("entwurf_bearbeiten", post_id=publication.post_id)) + "?planned=1"
    return RedirectResponse(url=url, status_code=303)
