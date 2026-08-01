from pathlib import Path

from playwright.sync_api import sync_playwright

from app.config import PLAYWRIGHT_PROFILE_DIR
from app.services.facebook_downloader import FacebookDownloader


class FacebookVideoResolver:
    """Findet die tatsächliche Videodatei hinter einem Facebook-/Reel-Link.

    Facebook-Seitenlinks sind keine direkt hochladbaren Videodateien. Deshalb wird
    die Seite kurz im Browser geöffnet, die Media-Antworten werden gesammelt und
    die beste Videodatei lokal im persistenten Upload-Ordner gespeichert.
    """

    def __init__(
        self,
        profile_dir: str | Path = PLAYWRIGHT_PROFILE_DIR,
        downloader: FacebookDownloader | None = None,
    ):
        self.profile_dir = Path(profile_dir)
        self.downloader = downloader or FacebookDownloader()

    def download_from_page(self, page_url: str) -> Path:
        cleaned_url = page_url.strip()
        if not cleaned_url.startswith(("http://", "https://")):
            raise RuntimeError("Der gespeicherte Video-Link ist ungültig.")

        candidates: list[tuple[str, int]] = []

        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=True,
                viewport={"width": 1400, "height": 1000},
                args=["--disable-dev-shm-usage"],
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()

                def collect_video_response(response) -> None:
                    try:
                        response_url = response.url
                        content_type = response.headers.get("content-type", "").lower()
                        resource_type = response.request.resource_type
                        if not (
                            resource_type == "media"
                            or content_type.startswith("video/")
                            or ".mp4" in response_url.lower()
                        ):
                            return
                        if response_url.startswith("blob:"):
                            return
                        size = int(response.headers.get("content-length", "0") or 0)
                        candidates.append((response_url, size))
                    except Exception:
                        pass

                page.on("response", collect_video_response)
                page.goto(cleaned_url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(12_000)

                # Das Video einmal starten, damit Facebook die Mediendatei anfordert.
                try:
                    video = page.locator("video").first
                    if video.count():
                        video.click(timeout=3_000)
                        page.wait_for_timeout(6_000)
                except Exception:
                    pass

                cookies = {
                    cookie["name"]: cookie["value"]
                    for cookie in context.cookies()
                }
                referer = page.url or cleaned_url
            finally:
                context.close()

        unique: dict[str, int] = {}
        for url, size in candidates:
            unique[url] = max(size, unique.get(url, 0))

        ordered = sorted(
            unique.items(),
            key=lambda item: (
                item[1],
                "hd_src" in item[0].lower(),
                ".mp4" in item[0].lower(),
            ),
            reverse=True,
        )

        if not ordered:
            raise RuntimeError(
                "Die tatsächliche Videodatei konnte hinter dem Facebook-Link nicht gefunden werden. "
                "Bitte den Videobeitrag erneut importieren oder einen direkten MP4-Link verwenden."
            )

        last_error: Exception | None = None
        for video_url, _ in ordered[:8]:
            try:
                return self.downloader.download_video(
                    video_url,
                    cookies=cookies,
                    referer=referer,
                )
            except Exception as exc:
                last_error = exc

        detail = f" ({last_error})" if last_error else ""
        raise RuntimeError(
            "Facebook hat zwar eine Videodatei geliefert, sie konnte aber nicht gespeichert werden"
            + detail
        )
