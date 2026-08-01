from collections import defaultdict
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.services.post_service import PostService
from app.services.publication_service import PublicationService
from app.services.publication_runner import PublicationRunner
from app.services.social_account_service import SocialAccountService


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
post_service = PostService()
publication_service = PublicationService()
account_service = SocialAccountService()
publication_runner = PublicationRunner()


def _available_texts(post) -> list[dict[str, str]]:
    values = [{
        "title": "Haupttext",
        "text": post.text.strip(),
    }]

    for variant in post.text_variants:
        text = str(variant.get("text", "")).strip()
        if not text:
            continue

        values.append({
            "title": (
                str(variant.get("title", "")).strip()
                or f"Variante {len(values)}"
            ),
            "text": text,
        })

    return values


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
async def publication_create(
    request: Request,
    post_id: str,
):
    post = post_service.get_post(post_id)
    if not post:
        raise HTTPException(
            status_code=404,
            detail="Beitrag nicht gefunden.",
        )

    form = await request.form()
    action = str(form.get("action", "plan")).strip().lower()
    account_ids = [
        str(value)
        for value in form.getlist("account_ids")
        if str(value).strip()
    ]

    if not account_ids:
        raise HTTPException(
            status_code=400,
            detail="Bitte mindestens eine Facebook-Seite auswählen.",
        )

    text_options = _available_texts(post)
    assignments: list[dict] = []
    invalid_accounts: list[str] = []

    for account_id in dict.fromkeys(account_ids):
        account = account_service.get(account_id)

        if not account or not account.active:
            invalid_accounts.append(account_id)
            continue

        raw_choice = str(
            form.get(f"variant_choice__{account_id}", "0")
        ).strip()

        try:
            choice = int(raw_choice)
        except ValueError:
            choice = 0

        if choice < 0 or choice >= len(text_options):
            choice = 0

        selected = text_options[choice]
        assignments.append({
            "account": account,
            "variant_title": selected["title"],
            "text": selected["text"],
        })

    if invalid_accounts:
        raise HTTPException(
            status_code=400,
            detail=(
                "Mindestens eine ausgewählte Seite "
                "ist nicht mehr verfügbar."
            ),
        )

    if action == "publish_now":
        publish_at = datetime.now().isoformat(timespec="seconds")
    else:
        publish_at = str(form.get("publish_at", "")).strip()

    try:
        created = publication_service.create_many(
            post_id=post_id,
            assignments=assignments,
            publish_at=publish_at,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    target = str(
        request.url_for(
            "entwurf_bearbeiten",
            post_id=post_id,
        )
    )

    if action != "publish_now":
        return RedirectResponse(
            url=target + f"?planned=1&planned_count={len(created)}",
            status_code=303,
        )

    published_count = 0
    failed_count = 0
    first_error = ""

    for publication in created:
        result = publication_runner.publish_one(publication.id)

        if result.status == "published":
            published_count += 1
        else:
            failed_count += 1
            if not first_error:
                first_error = (
                    result.error_message
                    or "Veröffentlichung fehlgeschlagen."
                )

    query = (
        f"published={1 if published_count else 0}"
        f"&published_count={published_count}"
        f"&failed_count={failed_count}"
    )

    if first_error:
        query += "&publish_error=" + quote(first_error)

    return RedirectResponse(
        url=target + "?" + query,
        status_code=303,
    )


@router.post("/publications/{publication_id}")
def publication_update(
    request: Request,
    publication_id: str,
    publish_at: str = Form(...),
    status: str = Form("planned"),
    publication_text: str = Form(""),
    variant_title: str = Form("Haupttext"),
):
    publication = publication_service.get(publication_id)

    if not publication:
        raise HTTPException(
            status_code=404,
            detail="Planung nicht gefunden.",
        )

    try:
        publication_service.update(
            publication_id,
            publish_at=publish_at,
            status=status,
            text=publication_text,
            variant_title=variant_title,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return RedirectResponse(
        url=(
            str(
                request.url_for(
                    "entwurf_bearbeiten",
                    post_id=publication.post_id,
                )
            )
            + "?planned=1"
        ),
        status_code=303,
    )


@router.post("/publications/{publication_id}/delete")
def publication_delete(
    request: Request,
    publication_id: str,
):
    publication = publication_service.get(publication_id)

    if not publication:
        raise HTTPException(
            status_code=404,
            detail="Planung nicht gefunden.",
        )

    publication_service.delete(publication_id)
    referer = request.headers.get("referer", "")

    if "/planning" in referer:
        url = (
            str(request.url_for("veroeffentlichungsplanung"))
            + "?deleted=1"
        )
    else:
        url = (
            str(
                request.url_for(
                    "entwurf_bearbeiten",
                    post_id=publication.post_id,
                )
            )
            + "?planned=1"
        )

    return RedirectResponse(url=url, status_code=303)
