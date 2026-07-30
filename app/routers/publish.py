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
