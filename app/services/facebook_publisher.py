import json
from pathlib import Path

import requests

from app.config import UPLOADS_DIR
from app.models.facebook_page import FacebookPage
from app.models.managed_post import ManagedPost
from app.services.facebook_api import (
    GRAPH_API_BASE_URL,
    FacebookApiError,
)
from app.services.settings_service import SettingsService


class FacebookPublisher:
    def __init__(
        self,
        settings_service: SettingsService | None = None,
    ):
        self.settings_service = settings_service or SettingsService()

    def publish(self, post: ManagedPost, page_id: str) -> str:
        page = self._get_page(page_id)
        if not page.access_token:
            raise FacebookApiError(
                "Für diese Facebook-Seite ist kein Zugriffstoken gespeichert. "
                "Bitte Facebook unter Einstellungen erneut verbinden."
            )

        video_link = self._get_video_link(post)
        if video_link:
            return self._publish_link(post, page, video_link)

        image_paths = [self._resolve_image_path(item) for item in post.images]
        image_paths = [path for path in image_paths if path is not None]

        if len(image_paths) == 1:
            return self._publish_single_photo(post, page, image_paths[0])
        if len(image_paths) > 1:
            return self._publish_multiple_photos(post, page, image_paths)

        # Medienmonitor-Linkbeitrag: eigener Begleittext + Originalartikel.
        # Eigene Bilder haben bewusst Vorrang; sobald ein Bild hinzugefügt wird,
        # wird daraus ein normaler Bildbeitrag statt eines Link-Shares.
        if (
            post.source_type == "media_monitor_share"
            and post.source_url.strip().startswith(("http://", "https://"))
        ):
            return self._publish_link(post, page, post.source_url.strip())

        return self._publish_text(post, page)

    @staticmethod
    def _get_video_link(post: ManagedPost) -> str:
        """Ermittelt den Original-Link eines Video- oder Reel-Beitrags.

        Videos werden bewusst weder heruntergeladen noch erneut hochgeladen.
        Der Original-Link wird gemeinsam mit dem importierten Beitragstext als
        normaler Facebook-Linkbeitrag veröffentlicht.
        """
        candidates = [post.video_url, *post.videos]

        for value in candidates:
            normalized = str(value).strip()
            if normalized.startswith(("http://", "https://")):
                return normalized

        return ""

    def _publish_link(
        self,
        post: ManagedPost,
        page: FacebookPage,
        link: str,
    ) -> str:
        data = self._request_json(
            url=f"{GRAPH_API_BASE_URL}/{page.page_id}/feed",
            data={
                "message": post.text.strip(),
                "link": link,
                "access_token": page.access_token,
            },
        )
        return self._require_post_id(data)

    def _get_page(self, page_id: str) -> FacebookPage:
        page = next(
            (item for item in self.settings_service.load_pages() if item.page_id == page_id),
            None,
        )
        if not page:
            raise FacebookApiError(
                "Die ausgewählte Facebook-Seite wurde nicht gefunden. "
                "Bitte Facebook unter Einstellungen erneut verbinden."
            )
        if not page.is_active:
            raise FacebookApiError("Die ausgewählte Facebook-Seite ist deaktiviert.")
        return page

    def _publish_text(self, post: ManagedPost, page: FacebookPage) -> str:
        if not post.text.strip():
            raise FacebookApiError("Der Beitrag enthält weder Text noch veröffentlichbare Bilder.")
        data = self._request_json(
            url=f"{GRAPH_API_BASE_URL}/{page.page_id}/feed",
            data={
                "message": post.text,
                "access_token": page.access_token,
            },
        )
        return self._require_post_id(data)

    def _publish_single_photo(
        self,
        post: ManagedPost,
        page: FacebookPage,
        image_path: Path,
    ) -> str:
        with image_path.open("rb") as image_file:
            data = self._request_json(
                url=f"{GRAPH_API_BASE_URL}/{page.page_id}/photos",
                data={
                    "message": post.text,
                    "access_token": page.access_token,
                },
                files={"source": (image_path.name, image_file)},
            )
        return self._require_post_id(data)

    def _publish_multiple_photos(
        self,
        post: ManagedPost,
        page: FacebookPage,
        image_paths: list[Path],
    ) -> str:
        media_ids: list[str] = []
        for image_path in image_paths:
            with image_path.open("rb") as image_file:
                upload = self._request_json(
                    url=f"{GRAPH_API_BASE_URL}/{page.page_id}/photos",
                    data={
                        "published": "false",
                        "access_token": page.access_token,
                    },
                    files={"source": (image_path.name, image_file)},
                )
            media_id = str(upload.get("id", "")).strip()
            if not media_id:
                raise FacebookApiError(
                    "Facebook hat für ein hochgeladenes Bild keine Medien-ID zurückgegeben."
                )
            media_ids.append(media_id)

        data = self._request_json(
            url=f"{GRAPH_API_BASE_URL}/{page.page_id}/feed",
            data={
                "message": post.text,
                "attached_media": json.dumps(
                    [{"media_fbid": media_id} for media_id in media_ids]
                ),
                "access_token": page.access_token,
            },
        )
        return self._require_post_id(data)

    @staticmethod
    def _resolve_image_path(value: str) -> Path | None:
        normalized = str(value).strip().replace("\\", "/")
        if not normalized or normalized.startswith(("http://", "https://")):
            return None

        marker = "uploads/"
        marker_position = normalized.find(marker)
        if marker_position >= 0:
            relative = normalized[marker_position + len(marker):]
            path = UPLOADS_DIR / relative
        else:
            path = Path(normalized)
            if not path.is_absolute():
                path = UPLOADS_DIR / normalized.lstrip("/")

        path = path.resolve()
        try:
            path.relative_to(UPLOADS_DIR.resolve())
        except ValueError as exc:
            raise FacebookApiError("Ein Bildpfad liegt außerhalb des Upload-Ordners.") from exc

        if not path.is_file():
            raise FacebookApiError(f"Das Bild wurde nicht gefunden: {path.name}")
        return path

    @staticmethod
    def _request_json(
        url: str,
        data: dict,
        files: dict | None = None,
        timeout: int = 60,
    ) -> dict:
        try:
            response = requests.post(url, data=data, files=files, timeout=timeout)
        except requests.RequestException as exc:
            raise FacebookApiError(f"Facebook konnte nicht erreicht werden: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise FacebookApiError("Facebook hat keine gültige Antwort zurückgegeben.") from exc

        if response.ok:
            return payload

        error_data = payload.get("error", {}) if isinstance(payload, dict) else {}
        message = (
            error_data.get("message", "Unbekannter Facebook-Fehler")
            if isinstance(error_data, dict)
            else str(error_data)
        )
        raise FacebookApiError(str(message))

    @staticmethod
    def _require_post_id(data: dict) -> str:
        post_id = str(data.get("post_id") or data.get("id") or "").strip()
        if not post_id:
            raise FacebookApiError("Facebook hat keine Beitrags-ID zurückgegeben.")
        return post_id
