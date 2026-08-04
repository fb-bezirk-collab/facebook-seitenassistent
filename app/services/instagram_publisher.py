from pathlib import Path
from uuid import uuid4
import math
import os
import time

import cloudinary
import cloudinary.uploader
from cloudinary.exceptions import Error as CloudinaryError
import requests
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import UPLOADS_DIR
from app.services.instagram_account_service import InstagramAccountService
from app.services.instagram_config_service import load_instagram_config
from app.services.instagram_api import InstagramApiError


class InstagramPublisher:
    """Veröffentlicht Bildbeiträge über die Instagram API mit Instagram Login."""

    api_version = "v23.0"
    graph_base_url = "https://graph.instagram.com"

    MIN_RATIO = 4 / 5
    MAX_RATIO = 1.91

    def __init__(self):
        self.accounts = InstagramAccountService()
        self.config = load_instagram_config()

        self.cloudinary_cloud_name = os.getenv(
            "CLOUDINARY_CLOUD_NAME",
            "",
        ).strip()
        self.cloudinary_api_key = os.getenv(
            "CLOUDINARY_API_KEY",
            "",
        ).strip()
        self.cloudinary_api_secret = os.getenv(
            "CLOUDINARY_API_SECRET",
            "",
        ).strip()

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

        prepared_image = self._prepare_image(
            post.images[0]
        )
        image_url = self._upload_to_cloudinary(
            prepared_image
        )

        print(
            "INSTAGRAM_PUBLISH|PREPARED_IMAGE|"
            + prepared_image,
            flush=True,
        )
        print(
            "INSTAGRAM_PUBLISH|CLOUDINARY_URL|"
            + image_url,
            flush=True,
        )

        print(
            "INSTAGRAM_PUBLISH|CONTAINER_REQUEST|"
            "single_image_form_token",
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
            },
            account.access_token,
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

        self._wait_for_container(
            creation_id=creation_id,
            access_token=account.access_token,
        )

        published = self._post(
            (
                f"{self.graph_base_url}/"
                f"{self.api_version}/"
                f"{instagram_id}/media_publish"
            ),
            {
                "creation_id": creation_id,
            },
            account.access_token,
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

    def _wait_for_container(
        self,
        *,
        creation_id: str,
        access_token: str,
        timeout_seconds: int = 90,
        interval_seconds: int = 2,
    ) -> None:
        """Wartet, bis Instagram den Mediencontainer fertig verarbeitet hat."""

        deadline = time.monotonic() + timeout_seconds
        last_status = ""

        while time.monotonic() < deadline:
            status_payload = self._get(
                (
                    f"{self.graph_base_url}/"
                    f"{self.api_version}/"
                    f"{creation_id}"
                ),
                {
                    "fields": "status_code,status",
                },
                access_token,
            )

            status_code = str(
                status_payload.get("status_code", "")
            ).strip().upper()

            status_text = str(
                status_payload.get("status", "")
            ).strip()

            if status_code != last_status:
                print(
                    "INSTAGRAM_PUBLISH|CONTAINER_STATUS|"
                    f"status_code={status_code or 'UNKNOWN'}|"
                    f"status={status_text}",
                    flush=True,
                )
                last_status = status_code

            if status_code == "FINISHED":
                return

            if status_code in {
                "ERROR",
                "EXPIRED",
            }:
                details = status_text or status_code
                raise InstagramApiError(
                    "Instagram konnte den Mediencontainer "
                    f"nicht fertig verarbeiten: {details}"
                )

            if status_code not in {
                "",
                "IN_PROGRESS",
                "PUBLISHED",
            }:
                print(
                    "INSTAGRAM_PUBLISH|CONTAINER_STATUS_UNKNOWN|"
                    f"{status_code}|{status_text}",
                    flush=True,
                )

            time.sleep(interval_seconds)

        raise InstagramApiError(
            "Instagram hat den Mediencontainer nicht rechtzeitig "
            "fertig verarbeitet. Bitte den Beitrag erneut veröffentlichen."
        )

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
            with Image.open(source_path) as source_image:
                source_image.load()

                # Berücksichtigt die in der Bilddatei gespeicherte Drehung.
                image = ImageOps.exif_transpose(
                    source_image
                )

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

                image = self._fit_supported_ratio(
                    image
                )

                image.save(
                    target_path,
                    format="JPEG",
                    quality=94,
                    optimize=False,
                    progressive=False,
                    subsampling=0,
                    dpi=(72, 72),
                )

                final_width, final_height = image.size

                print(
                    "INSTAGRAM_PUBLISH|IMAGE_DIMENSIONS|"
                    f"original={width}x{height}|"
                    f"prepared={final_width}x{final_height}|"
                    f"ratio={final_width / final_height:.6f}",
                    flush=True,
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

    def _upload_to_cloudinary(
        self,
        image_path: str,
    ) -> str:
        missing_variables = [
            name
            for name, value in (
                (
                    "CLOUDINARY_CLOUD_NAME",
                    self.cloudinary_cloud_name,
                ),
                (
                    "CLOUDINARY_API_KEY",
                    self.cloudinary_api_key,
                ),
                (
                    "CLOUDINARY_API_SECRET",
                    self.cloudinary_api_secret,
                ),
            )
            if not value
        ]

        if missing_variables:
            raise InstagramApiError(
                "Cloudinary ist nicht vollständig eingerichtet. "
                "In Railway fehlen folgende Variablen: "
                + ", ".join(missing_variables)
            )

        local_path = self._local_upload_path(
            image_path
        )

        if not local_path.exists():
            raise InstagramApiError(
                "Das für Cloudinary vorbereitete Bild "
                "wurde lokal nicht gefunden."
            )

        cloudinary.config(
            cloud_name=self.cloudinary_cloud_name,
            api_key=self.cloudinary_api_key,
            api_secret=self.cloudinary_api_secret,
            secure=True,
        )

        try:
            upload_result = cloudinary.uploader.upload(
                str(local_path),
                folder="facebook-seitenassistent/instagram",
                resource_type="image",
                type="upload",
                overwrite=False,
                unique_filename=True,
                use_filename=False,
            )
        except CloudinaryError as exc:
            raise InstagramApiError(
                "Das Bild konnte nicht zu Cloudinary "
                f"hochgeladen werden: {exc}"
            ) from exc
        except Exception as exc:
            raise InstagramApiError(
                "Beim Cloudinary-Upload ist ein "
                f"unerwarteter Fehler aufgetreten: {exc}"
            ) from exc

        secure_url = str(
            upload_result.get("secure_url", "")
        ).strip()

        if not secure_url:
            raise InstagramApiError(
                "Cloudinary hat keine öffentliche HTTPS-Bildadresse geliefert."
            )

        if not secure_url.startswith("https://"):
            raise InstagramApiError(
                "Cloudinary hat keine sichere HTTPS-Bildadresse geliefert."
            )

        print(
            "INSTAGRAM_PUBLISH|CLOUDINARY_UPLOAD|"
            f"public_id={upload_result.get('public_id', '')}|"
            f"format={upload_result.get('format', '')}|"
            f"bytes={upload_result.get('bytes', '')}",
            flush=True,
        )

        return secure_url

    def _fit_supported_ratio(
        self,
        image: Image.Image,
    ) -> Image.Image:
        """Passt das Bild ohne Abschneiden an den erlaubten Bereich an."""

        width, height = image.size
        ratio = width / height

        if (
            self.MIN_RATIO
            <= ratio
            <= self.MAX_RATIO
        ):
            return image

        if ratio < self.MIN_RATIO:
            # Zu hoch: links und rechts minimal erweitern.
            target_width = math.ceil(
                height * self.MIN_RATIO
            )
            target_height = height
        else:
            # Zu breit: oben und unten minimal erweitern.
            target_width = width
            target_height = math.ceil(
                width / self.MAX_RATIO
            )

        # Hintergrund aus den Bildecken ableiten, damit die Ergänzung
        # möglichst unauffällig bleibt.
        corner_pixels = [
            image.getpixel((0, 0)),
            image.getpixel((width - 1, 0)),
            image.getpixel((0, height - 1)),
            image.getpixel((width - 1, height - 1)),
        ]

        background_color = tuple(
            sum(pixel[channel] for pixel in corner_pixels)
            // len(corner_pixels)
            for channel in range(3)
        )

        canvas = Image.new(
            "RGB",
            (target_width, target_height),
            background_color,
        )

        left = (
            target_width - width
        ) // 2
        top = (
            target_height - height
        ) // 2

        canvas.paste(
            image,
            (left, top),
        )

        return canvas

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

    @staticmethod
    def _get(
        url: str,
        params: dict,
        access_token: str,
    ) -> dict:
        request_params = dict(params)
        request_params["access_token"] = access_token

        try:
            response = requests.get(
                url,
                params=request_params,
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

    @staticmethod
    def _post(
        url: str,
        payload: dict,
        access_token: str,
    ) -> dict:
        request_data = dict(payload)
        request_data["access_token"] = access_token

        try:
            response = requests.post(
                url,
                data=request_data,
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
