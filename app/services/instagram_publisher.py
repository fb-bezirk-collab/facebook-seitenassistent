from urllib.parse import quote

import requests

from app.services.instagram_account_service import InstagramAccountService
from app.services.instagram_config_service import load_instagram_config
from app.services.instagram_api import InstagramApiError


class InstagramPublisher:
    """Veröffentlicht Bildbeiträge über die Instagram API mit Instagram Login."""

    api_version = "v23.0"
    graph_base_url = "https://graph.instagram.com"

    def __init__(self):
        self.accounts = InstagramAccountService()
        self.config = load_instagram_config()

    def publish(
        self,
        *,
        post,
        instagram_id: str,
        caption: str,
    ) -> str:
        account = self.accounts.get(instagram_id)

        if not account or not account.access_token:
            raise InstagramApiError(
                "Instagram-Konto ist nicht verbunden."
            )

        if post.video_url or post.videos:
            raise InstagramApiError(
                "Instagram-Videos sind in dieser Version noch nicht möglich. "
                "Instagram benötigt eine öffentlich abrufbare Videodatei; "
                "ein Facebook-Reel-Link reicht nicht."
            )

        if not post.images:
            raise InstagramApiError(
                "Instagram benötigt mindestens ein Bild."
            )

        if not self.config.public_base_url:
            raise InstagramApiError(
                "PUBLIC_BASE_URL beziehungsweise "
                "INSTAGRAM_REDIRECT_URI fehlt."
            )

        image_url = self._public_image_url(post.images[0])

        print(
            "INSTAGRAM_PUBLISH|IMAGE_URL|"
            + image_url,
            flush=True,
        )

        # Wichtig:
        # Kein requests.get() oder requests.head() auf die eigene Railway-URL.
        # Instagram lädt das Bild selbst über image_url.
        container = self._post(
            (
                f"{self.graph_base_url}/"
                f"{self.api_version}/"
                f"{instagram_id}/media"
            ),
            {
                "image_url": image_url,
                "caption": caption.strip(),
                "access_token": account.access_token,
            },
        )

        creation_id = str(
            container.get("id", "")
        ).strip()

        if not creation_id:
            raise InstagramApiError(
                "Instagram hat keinen Mediencontainer erstellt."
            )

        print(
            "INSTAGRAM_PUBLISH|CONTAINER_CREATED|"
            + creation_id,
            flush=True,
        )

        published = self._post(
            (
                f"{self.graph_base_url}/"
                f"{self.api_version}/"
                f"{instagram_id}/media_publish"
            ),
            {
                "creation_id": creation_id,
                "access_token": account.access_token,
            },
        )

        media_id = str(
            published.get("id", "")
        ).strip()

        if not media_id:
            raise InstagramApiError(
                "Instagram hat keine Beitrags-ID geliefert."
            )

        print(
            "INSTAGRAM_PUBLISH|PUBLISHED|"
            + media_id,
            flush=True,
        )

        return media_id

    def _public_image_url(
        self,
        image_path: str,
    ) -> str:
        normalized = str(image_path).replace(
            "\\",
            "/",
        )

        marker = "uploads/"
        position = normalized.find(marker)

        if position < 0:
            raise InstagramApiError(
                "Das Bild liegt nicht im öffentlichen Upload-Ordner."
            )

        relative_path = normalized[position:]

        return (
            self.config.public_base_url.rstrip("/")
            + "/"
            + quote(
                relative_path,
                safe="/",
            )
        )

    @staticmethod
    def _post(
        url: str,
        data: dict,
    ) -> dict:
        try:
            response = requests.post(
                url,
                data=data,
                timeout=90,
            )
        except requests.RequestException as exc:
            raise InstagramApiError(
                f"Instagram ist nicht erreichbar: {exc}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise InstagramApiError(
                "Instagram hat keine gültige Antwort geliefert."
            ) from exc

        if response.status_code >= 400:
            error = payload.get("error", {})

            if isinstance(error, dict):
                message = str(
                    error.get("message", "")
                ).strip()
                error_type = str(
                    error.get("type", "")
                ).strip()
                error_code = error.get("code")
                error_subcode = error.get(
                    "error_subcode"
                )

                details = [
                    value
                    for value in (
                        message,
                        (
                            f"Typ: {error_type}"
                            if error_type
                            else ""
                        ),
                        (
                            f"Code: {error_code}"
                            if error_code is not None
                            else ""
                        ),
                        (
                            f"Subcode: {error_subcode}"
                            if error_subcode is not None
                            else ""
                        ),
                    )
                    if value
                ]

                if details:
                    raise InstagramApiError(
                        " · ".join(details)
                    )

            raise InstagramApiError(
                response.text.strip()
                or f"Instagram-Fehler HTTP {response.status_code}"
            )

        return payload
