from pathlib import Path
from urllib.parse import quote

import requests

from app.services.instagram_account_service import InstagramAccountService
from app.services.instagram_config_service import load_instagram_config
from app.services.instagram_api import InstagramApiError


class InstagramPublisher:
    api_version = "v23.0"

    def __init__(self):
        self.accounts = InstagramAccountService()
        self.config = load_instagram_config()

    def publish(self, *, post, instagram_id: str, caption: str) -> str:
        account = self.accounts.get(instagram_id)
        if not account or not account.access_token:
            raise InstagramApiError("Instagram-Konto ist nicht verbunden.")
        if post.video_url or post.videos:
            raise InstagramApiError(
                "Instagram-Videos sind in dieser Version noch nicht möglich. "
                "Instagram benötigt eine öffentlich abrufbare Videodatei; ein Facebook-Reel-Link reicht nicht."
            )
        if not post.images:
            raise InstagramApiError("Instagram benötigt mindestens ein Bild.")
        if not self.config.public_base_url:
            raise InstagramApiError("PUBLIC_BASE_URL bzw. INSTAGRAM_REDIRECT_URI fehlt.")

        image_url = self._public_image_url(post.images[0])

        debug = requests.get(image_url, timeout=30)
        print("IG_DEBUG", {"url": image_url, "status": debug.status_code, "content_type": debug.headers.get("Content-Type"), "length": debug.headers.get("Content-Length")})
        container = self._post(
            f"https://graph.facebook.com/{self.api_version}/{instagram_id}/media",
            {
                "image_url": image_url,
                "media_type": "IMAGE",
                "caption": caption,
                "access_token": account.access_token,
            },
        )
        creation_id = str(container.get("id", "")).strip()
        if not creation_id:
            raise InstagramApiError("Instagram hat keinen Mediencontainer erstellt.")

        published = self._post(
            f"https://graph.facebook.com/{self.api_version}/{instagram_id}/media_publish",
            {
                "creation_id": creation_id,
                "access_token": account.access_token,
            },
        )
        media_id = str(published.get("id", "")).strip()
        if not media_id:
            raise InstagramApiError("Instagram hat keine Beitrags-ID geliefert.")
        return media_id

    def _public_image_url(self, image_path: str) -> str:
        normalized = str(image_path).replace("\\", "/")
        marker = "uploads/"
        pos = normalized.find(marker)
        if pos < 0:
            raise InstagramApiError("Das Bild liegt nicht im öffentlichen Upload-Ordner.")
        relative = normalized[pos:]
        return self.config.public_base_url.rstrip("/") + "/" + quote(relative, safe="/")

    @staticmethod
    def _post(url: str, data: dict) -> dict:
        try:
            response = requests.post(url, data=data, timeout=60)
        except requests.RequestException as exc:
            raise InstagramApiError(f"Instagram ist nicht erreichbar: {exc}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise InstagramApiError("Instagram hat keine gültige Antwort geliefert.") from exc
        if response.status_code >= 400:
            error = payload.get("error", {})
            message = error.get("message") if isinstance(error, dict) else None
            raise InstagramApiError(str(message or response.text or response.status_code))
        return payload
