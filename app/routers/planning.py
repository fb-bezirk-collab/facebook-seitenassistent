from collections import defaultdict
import json
from datetime import datetime, timedelta, timezone
import random
from urllib.parse import quote
from zoneinfo import ZoneInfo

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

LOCAL_TIMEZONE = ZoneInfo("Europe/Vienna")
MONTH_NAMES = {
    1: "Jänner",
    2: "Februar",
    3: "März",
    4: "April",
    5: "Mai",
    6: "Juni",
    7: "Juli",
    8: "August",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Dezember",
}


def _parse_submitted_variants(
    raw_value: str,
) -> list[dict[str, str]]:
    if not raw_value.strip():
        return []

    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return []

    if not isinstance(value, list):
        return []

    variants: list[dict[str, str]] = []

    for index, item in enumerate(value[:8], start=1):
        if not isinstance(item, dict):
            continue

        text = str(item.get("text", "")).strip()
        if not text:
            continue

        title = (
            str(item.get("title", "")).strip()
            or f"Variante {index}"
        )

        variants.append({
            "title": title,
            "text": text,
        })

    return variants


def _distributed_times(
    *,
    start_value: str,
    end_value: str,
    count: int,
    mode: str,
) -> list[str]:
    """Verteilt Termine gleichmäßig oder zufällig innerhalb eines Zeitraums."""
    if count <= 0:
        return []

    try:
        start = datetime.fromisoformat(start_value)
        end = datetime.fromisoformat(end_value)
    except ValueError as exc:
        raise ValueError(
            "Beginn oder Ende des Zeitraums ist ungültig."
        ) from exc

    if end < start:
        raise ValueError(
            "Das Ende des Zeitraums muss nach dem Beginn liegen."
        )

    if count == 1 or start == end:
        return [start.isoformat(timespec="minutes")] * count

    total_seconds = (end - start).total_seconds()

    if mode == "random":
        offsets = sorted(
            random.uniform(0, total_seconds)
            for _ in range(count)
        )
    else:
        step = total_seconds / (count - 1)
        offsets = [
            step * index
            for index in range(count)
        ]

    return [
        (start + timedelta(seconds=offset)).isoformat(
            timespec="minutes"
        )
        for offset in offsets
    ]


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


def _to_local_datetime(value: str, *, assume_utc: bool = False) -> datetime | None:
    """Wandelt gespeicherte ISO-Zeitwerte zuverlässig in Wiener Zeit um."""
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc if assume_utc else LOCAL_TIMEZONE
        )

    return parsed.astimezone(LOCAL_TIMEZONE)


def _publication_display_datetime(publication) -> datetime:
    """Für veröffentlichte Beiträge gilt der tatsächliche Veröffentlichungszeitpunkt."""
    if publication.status == "published" and publication.published_at:
        published = _to_local_datetime(
            publication.published_at,
            assume_utc=True,
        )
        if published is not None:
            return published

    planned = _to_local_datetime(publication.publish_at)
    if planned is not None:
        return planned

    return datetime.now(LOCAL_TIMEZONE)


def _group_publications(publications: list) -> list[dict]:
    months: dict[str, dict] = {}

    for publication in publications:
        display_datetime = _publication_display_datetime(publication)
        month_key = display_datetime.strftime("%Y-%m")
        day_key = display_datetime.strftime("%Y-%m-%d")

        month = months.setdefault(
            month_key,
            {
                "key": month_key,
                "label": (
                    f"{MONTH_NAMES[display_datetime.month]} "
                    f"{display_datetime.year}"
                ),
                "count": 0,
                "days": {},
            },
        )

        day = month["days"].setdefault(
            day_key,
            {
                "key": day_key,
                "label": display_datetime.strftime("%d.%m.%Y"),
                "count": 0,
                "entries": [],
            },
        )

        row = {
            "publication": publication,
            "display_time": display_datetime.strftime("%H:%M"),
            "display_datetime": display_datetime,
        }

        day["entries"].append(row)
        day["count"] += 1
        month["count"] += 1

    result: list[dict] = []

    for month_key in sorted(months, reverse=True):
        month = months[month_key]
        days: list[dict] = []

        for day_key in sorted(month["days"], reverse=True):
            day = month["days"][day_key]
            day["entries"].sort(
                key=lambda row: row["display_datetime"],
                reverse=True,
            )
            days.append(day)

        month["days"] = days
        result.append(month)

    return result


@router.get("/planning", name="veroeffentlichungsplanung")
def planning(
    request: Request,
    saved: int = 0,
    deleted: int = 0,
    deleted_count: int = 0,
    published: int = 0,
    publish_error: str | None = None,
):
    publications = publication_service.list_publications()
    posts = {post.id: post for post in post_service.list_posts()}
    grouped_months = _group_publications(publications)

    return templates.TemplateResponse(
        request=request,
        name="planning.html",
        context={
            "publications": publications,
            "posts": posts,
            "grouped_months": grouped_months,
            "saved": bool(saved),
            "deleted": bool(deleted),
            "deleted_count": deleted_count,
            "published": bool(published),
            "publish_error": publish_error,
            "now": datetime.now(LOCAL_TIMEZONE).isoformat(timespec="minutes"),
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

    submitted_variants = _parse_submitted_variants(
        str(form.get("text_variants_json", ""))
    )

    if submitted_variants:
        updated_post = post_service.update_draft(
            post_id,
            title=post.title,
            text=post.text,
            text_variants=submitted_variants,
            images=post.images,
            videos=post.videos,
            video_url=post.video_url,
            page_id=post.page_id,
            source_url=post.source_url,
        )

        if updated_post:
            post = updated_post

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
        publish_at = datetime.now(LOCAL_TIMEZONE).isoformat(timespec="seconds")
    else:
        distribution_enabled = (
            str(form.get("distribute_times", "")).strip() == "1"
        )

        if distribution_enabled:
            start_value = str(
                form.get("distribution_start", "")
            ).strip()
            end_value = str(
                form.get("distribution_end", "")
            ).strip()
            distribution_mode = str(
                form.get("distribution_mode", "even")
            ).strip().lower()

            if distribution_mode not in {"even", "random"}:
                distribution_mode = "even"

            try:
                distributed_times = _distributed_times(
                    start_value=start_value,
                    end_value=end_value,
                    count=len(assignments),
                    mode=distribution_mode,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=str(exc),
                ) from exc

            for assignment, assigned_time in zip(
                assignments,
                distributed_times,
            ):
                assignment["publish_at"] = assigned_time

            publish_at = start_value
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
            + "?deleted=1&deleted_count=1"
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


@router.post("/planning/day/{day_key}/delete")
def publication_day_delete(
    request: Request,
    day_key: str,
):
    try:
        datetime.strptime(day_key, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Ungültiges Datum.",
        ) from exc

    publication_ids = [
        publication.id
        for publication in publication_service.list_publications()
        if _publication_display_datetime(publication).strftime("%Y-%m-%d")
        == day_key
    ]

    deleted_count = publication_service.delete_many(publication_ids)

    return RedirectResponse(
        url=(
            str(request.url_for("veroeffentlichungsplanung"))
            + f"?deleted=1&deleted_count={deleted_count}"
        ),
        status_code=303,
    )
