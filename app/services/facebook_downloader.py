from pathlib import Path
from urllib.parse import urlparse

import requests

from app.services.media_storage import MediaStorage


class FacebookDownloader:
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )

    def __init__(self, storage: MediaStorage | None = None):
        self.storage = storage or MediaStorage()

    def download_image(
        self,
        image_url: str,
        cookies: dict[str, str] | None = None,
        referer: str | None = None,
    ) -> Path:
        response = requests.get(
            image_url,
            timeout=60,
            headers=self._headers(referer),
            cookies=cookies,
        )
        response.raise_for_status()

        file_extension = self._detect_image_extension(
            image_url=image_url,
            content_type=response.headers.get("content-type", ""),
        )
        file_path = self.storage.create_file_path(file_extension)
        file_path.write_bytes(response.content)
        return file_path

    def download_video(
        self,
        video_url: str,
        cookies: dict[str, str] | None = None,
        referer: str | None = None,
        max_bytes: int = 750 * 1024 * 1024,
    ) -> Path:
        with requests.get(
            video_url,
            timeout=(30, 300),
            headers=self._headers(referer),
            cookies=cookies,
            stream=True,
        ) as response:
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()
            if not (
                content_type.startswith("video/")
                or "application/octet-stream" in content_type
                or self._looks_like_video_url(video_url)
            ):
                raise RuntimeError(
                    f"Die gefundene Datei ist kein Video ({content_type or 'unbekannter Typ'})."
                )

            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                raise RuntimeError("Das Video ist größer als 750 MB.")

            extension = self._detect_video_extension(video_url, content_type)
            file_path = self.storage.create_file_path(extension)
            written = 0

            try:
                with file_path.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > max_bytes:
                            raise RuntimeError("Das Video ist größer als 750 MB.")
                        output.write(chunk)
            except Exception:
                file_path.unlink(missing_ok=True)
                raise

        if written == 0:
            file_path.unlink(missing_ok=True)
            raise RuntimeError("Das Video wurde leer heruntergeladen.")

        return file_path

    @classmethod
    def _headers(cls, referer: str | None) -> dict[str, str]:
        headers = {
            "User-Agent": cls.USER_AGENT,
            "Accept": "*/*",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    @staticmethod
    def _detect_image_extension(image_url: str, content_type: str) -> str:
        content_type = content_type.lower()
        if "image/jpeg" in content_type:
            return "jpg"
        if "image/png" in content_type:
            return "png"
        if "image/webp" in content_type:
            return "webp"

        suffix = Path(urlparse(image_url).path).suffix.lower().lstrip(".")
        if suffix in {"jpg", "jpeg", "png", "webp"}:
            return "jpg" if suffix == "jpeg" else suffix
        return "jpg"

    @classmethod
    def _detect_video_extension(cls, video_url: str, content_type: str) -> str:
        if "video/webm" in content_type:
            return "webm"
        if "video/quicktime" in content_type:
            return "mov"
        if "video/x-m4v" in content_type:
            return "m4v"

        suffix = Path(urlparse(video_url).path).suffix.lower().lstrip(".")
        if suffix in {"mp4", "webm", "mov", "m4v"}:
            return suffix
        return "mp4"

    @staticmethod
    def _looks_like_video_url(url: str) -> bool:
        lower = url.lower()
        return any(marker in lower for marker in (".mp4", ".webm", ".mov", "video"))
