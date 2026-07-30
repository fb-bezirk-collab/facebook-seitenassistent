from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.services.publication_runner import PublicationRunner
from app.services.publication_service import PublicationService


router = APIRouter(prefix="/publish", tags=["Veröffentlichung"])
runner = PublicationRunner()
publication_service = PublicationService()


@router.post("/{publication_id}/now")
def jetzt_veroeffentlichen(request: Request, publication_id: str):
    publication = publication_service.get(publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Planung nicht gefunden.")

    result = runner.publish_one(publication_id)
    if result.status == "published":
        query = "published=1"
    else:
        query = "publish_error=" + quote(result.error_message or "Veröffentlichung fehlgeschlagen.")

    referer = request.headers.get("referer", "")
    if "/planning" in referer:
        target = str(request.url_for("veroeffentlichungsplanung"))
    else:
        target = str(request.url_for("entwurf_bearbeiten", post_id=result.post_id))

    return RedirectResponse(
        url=target + "?" + query,
        status_code=303,
    )


@router.post("/post/{post_id}/now")
def beitrag_jetzt_auf_allen_seiten_veroeffentlichen(request: Request, post_id: str):
    publications = [
        item for item in publication_service.list_publications(post_id)
        if item.status not in {"published", "cancelled"}
    ]
    if not publications:
        raise HTTPException(status_code=400, detail="Für diesen Beitrag gibt es keine offenen Veröffentlichungen.")

    published_count = 0
    failed_count = 0
    first_error = ""

    for publication in publications:
        result = runner.publish_one(publication.id)
        if result.status == "published":
            published_count += 1
        else:
            failed_count += 1
            if not first_error:
                first_error = result.error_message or "Veröffentlichung fehlgeschlagen."

    target = str(request.url_for("entwurf_bearbeiten", post_id=post_id))
    query = (
        f"published={1 if published_count else 0}"
        f"&published_count={published_count}"
        f"&failed_count={failed_count}"
    )
    if first_error:
        query += "&publish_error=" + quote(first_error)

    return RedirectResponse(url=target + "?" + query, status_code=303)
