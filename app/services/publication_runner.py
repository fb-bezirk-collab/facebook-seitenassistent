import threading
from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.models.publication import Publication, utc_now_iso
from app.services.facebook_api import FacebookApiError
from app.services.facebook_publisher import FacebookPublisher
from app.services.post_service import PostService
from app.services.instagram_api import InstagramApiError
from app.services.instagram_publisher import InstagramPublisher
from app.services.publication_service import PublicationService


LOCAL_TIMEZONE = ZoneInfo("Europe/Vienna")


class PublicationRunner:
    _lock = threading.Lock()

    def __init__(
        self,
        publication_service: PublicationService | None = None,
        post_service: PostService | None = None,
        facebook_publisher: FacebookPublisher | None = None,
        instagram_publisher: InstagramPublisher | None = None,
    ):
        self.publication_service = publication_service or PublicationService()
        self.post_service = post_service or PostService()
        self.facebook_publisher = facebook_publisher or FacebookPublisher()
        self.instagram_publisher = instagram_publisher or InstagramPublisher()

    def publish_one(self, publication_id: str) -> Publication:
        with self._lock:
            publication = self.publication_service.get(publication_id)
            if not publication:
                raise ValueError("Planung nicht gefunden.")
            if publication.status == "published":
                return publication
            return self._execute(publication)

    def publish_due(self) -> int:
        if not self._lock.acquire(blocking=False):
            return 0
        try:
            published_count = 0
            now = datetime.now(LOCAL_TIMEZONE)
            for publication in self.publication_service.list_publications():
                if publication.status not in {"planned", "ready"}:
                    continue
                if not self._is_due(publication.publish_at, now):
                    continue
                result = self._execute(publication)
                if result.status == "published":
                    published_count += 1
            return published_count
        finally:
            self._lock.release()

    def _execute(self, publication: Publication) -> Publication:
        post = self.post_service.get_post(publication.post_id)
        if not post:
            return self.publication_service.mark_failed(
                publication.id,
                "Der zugehörige Entwurf wurde nicht gefunden.",
            ) or publication

        try:
            publication_post = replace(
                post,
                text=publication.text.strip() or post.text,
            )
            if publication.platform == "facebook":
                external_post_id = self.facebook_publisher.publish(
                    post=publication_post,
                    page_id=publication.account_id.removeprefix("facebook:"),
                )
            elif publication.platform == "instagram":
                external_post_id = self.instagram_publisher.publish(
                    post=publication_post,
                    instagram_id=publication.account_id.removeprefix("instagram:"),
                    caption=publication_post.text,
                )
            else:
                return self.publication_service.mark_failed(
                    publication.id,
                    f"Automatisches Veröffentlichen auf {publication.platform} ist noch nicht verfügbar.",
                ) or publication
        except (FacebookApiError, InstagramApiError, OSError, ValueError) as exc:
            return self.publication_service.mark_failed(
                publication.id,
                str(exc),
            ) or publication

        return self.publication_service.mark_published(
            publication.id,
            external_post_id=external_post_id,
            published_at=utc_now_iso(),
        ) or publication

    @staticmethod
    def _is_due(value: str, now: datetime) -> bool:
        try:
            planned = datetime.fromisoformat(value)
        except ValueError:
            return False
        if planned.tzinfo is None:
            planned = planned.replace(tzinfo=LOCAL_TIMEZONE)
        return planned <= now
