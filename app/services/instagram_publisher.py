from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import requests
from PIL import Image, UnidentifiedImageError

from app.config import UPLOADS_DIR
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

        prepared_image = self._prepare_image(
            post.images[0]
        )
        image_url = self._public_image_url(
            prepared_image
        )

        print(
            "INSTAGRAM_PUBLISH|PREPARED_IMAGE|"
            + prepared_image,
            flush=True,
        )
        print(
            "INSTAGRAM_PUBLISH|IMAGE_URL|"
            + image_url,
            flush=True,
        )

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

    def _prepare_image(
        self,
        image_path: str,
    ) -> str:
        source_path = self._local_upload_path(
            image_path
        )

        if not source_path.exists():
            raise InstagramApiError(
                "Die lokale Bilddatei wurde nicht gefunden."
            )

        target_directory = (
            UPLOADS_DIR
            / "instagram"
            / "prepared"
        )
        target_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        target_path = (
            target_directory
            / f"{uuid4().hex}.jpg"
        )

        try:
            with Image.open(source_path) as image:
                image.load()

                if image.mode in {"RGBA", "LA"}:
                    background = Image.new(
                        "RGB",
                        image.size,
                        "white",
                    )
                    alpha = image.getchannel("A")
                    background.paste(
                        image.convert("RGB"),
                        mask=alpha,
                    )
                    image = background
                elif image.mode != "RGB":
                    image = image.convert("RGB")

                width, height = image.size

                if width < 320 or height < 320:
                    raise InstagramApiError(
                        "Das Bild ist für Instagram zu klein. "
                        "Mindestens 320 × 320 Pixel sind erforderlich."
                    )

                ratio = width / height

                # Instagram Feed: Seitenverhältnis 4:5 bis 1.91:1.
                if ratio < 0.8 or ratio > 1.91:
                    raise InstagramApiError(
                        "Das Bildseitenverhältnis wird von Instagram "
                        "nicht unterstützt. Zulässig sind 4:5 bis 1,91:1."
                    )

                image.save(
                    target_path,
                    format="JPEG",
                    quality=92,
                    optimize=False,
                    progressive=False,
                    subsampling=0,
                    dpi=(72, 72),
                )

        except InstagramApiError:
            raise
        except (
            OSError,
            UnidentifiedImageError,
        ) as exc:
            raise InstagramApiError(
                "Das Bild konnte nicht für Instagram "
                f"aufbereitet werden: {exc}"
            ) from exc

        return target_path.relative_to(
            UPLOADS_DIR.parent
        ).as_posix()

    @staticmethod
    def _local_upload_path(
        image_path: str,
    ) -> Path:
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

        relative_inside_uploads = normalized[
            position + len(marker):
        ]

        return (
            UPLOADS_DIR
            / relative_inside_uploads
        ).resolve()

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
                "Das vorbereitete Bild liegt nicht im "
                "öffentlichen Upload-Ordner."
            )

        relative_path = normalized[position:]

        return (
            self.config.public_base_url.rstrip("/")
            + "/"
            + quote(
                relative_path,
                safe="/",
            )
            + "?ig="
            + uuid4().hex
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
                or (
                    "Instagram-Fehler HTTP "
                    f"{response.status_code}"
                )
            )

        return payload
