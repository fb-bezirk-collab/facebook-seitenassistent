import os
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from app.config import PLAYWRIGHT_PROFILE_DIR
from app.models.facebook_post import FacebookPost
from app.services.facebook_downloader import FacebookDownloader


class FacebookImporter:
    def __init__(
        self,
        profile_dir: str | Path = PLAYWRIGHT_PROFILE_DIR,
        headless: bool | None = None,
        downloader: FacebookDownloader | None = None,
    ):
        self.profile_dir = Path(profile_dir)
        if headless is None:
            configured = os.getenv("PLAYWRIGHT_HEADLESS", "").strip().lower()
            if configured:
                headless = configured in {"1", "true", "yes", "on"}
            else:
                headless = bool(os.getenv("RAILWAY_ENVIRONMENT"))
        self.headless = headless
        self.downloader = downloader or FacebookDownloader()

    def import_from_url(
        self,
        url: str,
        *,
        import_type: str = "image",
        video_url: str = "",
    ) -> FacebookPost:
        cleaned_url = self._clean_url(url)
        if import_type == "video":
            return self._import_video_link_post(cleaned_url, video_url)
        return self._import_image_post(cleaned_url)

    def _import_image_post(self, url: str) -> FacebookPost:
        image_urls: set[str] = set()

        with sync_playwright() as playwright:
            context = self._launch_context(playwright)
            try:
                page = context.pages[0] if context.pages else context.new_page()

                def collect_image_response(response) -> None:
                    try:
                        response_url = response.url
                        if (
                            response.request.resource_type == "image"
                            and "fbcdn.net" in response_url
                        ):
                            image_urls.add(response_url)
                    except Exception:
                        pass

                page.on("response", collect_image_response)
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(8_000)

                posts = page.locator("div[role='article']")
                if posts.count() == 0:
                    raise RuntimeError(
                        "Auf der Facebook-Seite wurde kein Bild-/Textbeitrag gefunden. "
                        "Für Reels oder Videos bitte 'Videobeitrag' auswählen."
                    )

                post = posts.first
                text = self._extract_article_text(post)
                cookies = self._cookies_as_dict(context)
                final_url = page.url or url

                local_images = self._download_images(
                    self._filter_post_images(image_urls),
                    cookies=cookies,
                    referer=final_url,
                )

                return FacebookPost(
                    text=text,
                    images=local_images,
                    videos=[],
                    video_url="",
                    source_url=final_url,
                )
            finally:
                context.close()

    def _import_video_link_post(self, text_url: str, video_url: str) -> FacebookPost:
        """Liest nur den Beitragstext und speichert einen Link zum Originalvideo.

        Das Video wird bewusst nicht heruntergeladen. Dadurch entstehen weder große
        Dateien noch Probleme mit Facebooks wechselnden Videoformaten und MIME-Typen.
        """
        requested_video_url = self._normalize_external_url(video_url)

        with sync_playwright() as playwright:
            context = self._launch_context(playwright)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(text_url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(10_000)

                # Facebook kürzt längere Beitragstexte zunächst mit "Mehr anzeigen".
                # Vor dem Auslesen wird diese Erweiterung gezielt im Hauptbeitrag
                # geöffnet, damit der vollständige Text gespeichert wird.
                self._expand_video_text(
                    page,
                    text_url=text_url,
                    video_url=requested_video_url,
                )

                final_url = page.url or text_url
                text = self._extract_video_text(
                    page,
                    text_url=text_url,
                    video_url=requested_video_url,
                )
                stored_video_url = requested_video_url or self._preferred_video_page_url(
                    page,
                    fallback=final_url,
                )

                if not stored_video_url:
                    raise RuntimeError(
                        "Es wurde kein Video-Link angegeben oder auf der Seite gefunden. "
                        "Bitte den Facebook-Reel-Link in das Feld 'Link zum Originalvideo' einfügen."
                    )

                return FacebookPost(
                    text=text,
                    images=[],
                    videos=[],
                    video_url=stored_video_url,
                    source_url=final_url,
                )
            finally:
                context.close()

    def _launch_context(self, playwright):
        return playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            viewport={"width": 1400, "height": 1000},
            args=["--disable-dev-shm-usage"],
        )

    @staticmethod
    def _extract_article_text(post) -> str:
        try:
            blocks = post.locator("div[dir='auto']").all_inner_texts()
        except Exception:
            return ""
        return FacebookImporter._best_text(blocks)

    @staticmethod
    def _video_id_from_url(url: str) -> str:
        """Liest die Facebook-Video-ID aus unterschiedlichen URL-Formen."""

        if not url:
            return ""

        patterns = (
            r"/reel/(\d+)",
            r"/videos/(\d+)",
            r"[?&]v=(\d+)",
            r"fb\.watch/([^/?#]+)",
        )

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return ""

    def _find_video_article(
        self,
        page,
        *,
        text_url: str = "",
        video_url: str = "",
    ):
        """Sucht den Artikel, der zur übergebenen Video-ID gehört."""

        video_ids = {
            value
            for value in (
                self._video_id_from_url(text_url),
                self._video_id_from_url(video_url),
            )
            if value
        }

        try:
            articles = page.locator("div[role='article']")
            article_count = articles.count()
        except Exception:
            return None

        if article_count == 0:
            return None

        if not video_ids:
            return articles.first

        for index in range(min(article_count, 15)):
            article = articles.nth(index)

            try:
                html = article.inner_html()
            except Exception:
                html = ""

            try:
                links = article.locator("a[href]").evaluate_all(
                    """
                    links => links
                        .map(link => link.href || "")
                        .filter(Boolean)
                    """
                )
            except Exception:
                links = []

            combined = " ".join([html, *links])

            if any(video_id in combined for video_id in video_ids):
                return article

        return articles.first

    def _expand_video_text(
        self,
        page,
        *,
        text_url: str = "",
        video_url: str = "",
    ) -> None:
        """Öffnet „Mehr anzeigen“ ausschließlich im passenden Video-Beitrag."""

        article = self._find_video_article(
            page,
            text_url=text_url,
            video_url=video_url,
        )

        if article is None:
            return

        labels = (
            "mehr anzeigen",
            "mehr ansehen",
            "see more",
            "voir plus",
            "mostra altro",
        )

        for _attempt in range(4):
            roots = []

            for selector in (
                "[data-ad-preview='message']",
                "[data-ad-comet-preview='message']",
            ):
                try:
                    locator = article.locator(selector)
                    for index in range(min(locator.count(), 5)):
                        roots.append(locator.nth(index))
                except Exception:
                    pass

            roots.append(article)
            clicked = False

            for root in roots:
                try:
                    buttons = root.locator(
                        "div[role='button'], "
                        "span[role='button'], "
                        "button, "
                        "[tabindex='0']"
                    )

                    for index in range(min(buttons.count(), 80)):
                        button = buttons.nth(index)

                        try:
                            label = " ".join(
                                (button.inner_text() or "").split()
                            ).strip().lower()
                        except Exception:
                            label = ""

                        if not label:
                            try:
                                label = " ".join(
                                    (
                                        button.get_attribute("aria-label") or ""
                                    ).split()
                                ).strip().lower()
                            except Exception:
                                label = ""

                        if not any(value in label for value in labels):
                            continue

                        try:
                            if button.is_visible():
                                button.click(timeout=3_000, force=True)
                                clicked = True
                                break
                        except Exception:
                            try:
                                button.evaluate("element => element.click()")
                                clicked = True
                                break
                            except Exception:
                                pass

                    if clicked:
                        break

                except Exception:
                    pass

            if clicked:
                page.wait_for_timeout(1_500)
            else:
                page.wait_for_timeout(1_000)

            try:
                message_nodes = article.locator(
                    "[data-ad-preview='message'], "
                    "[data-ad-comet-preview='message']"
                )

                visible_texts = []

                for index in range(min(message_nodes.count(), 5)):
                    try:
                        value = message_nodes.nth(index).inner_text()
                        if value:
                            visible_texts.append(value)
                    except Exception:
                        pass

                if visible_texts:
                    best = self._best_plausible_text(visible_texts)
                    if best and not self._looks_truncated(best):
                        return
            except Exception:
                pass

    def _extract_video_text(
        self,
        page,
        *,
        text_url: str = "",
        video_url: str = "",
    ) -> str:
        """Liest den vollständigsten Text aus dem passenden Video-Beitrag."""

        article = self._find_video_article(
            page,
            text_url=text_url,
            video_url=video_url,
        )

        all_candidates: list[str] = []

        if article is not None:
            for selector in (
                "[data-ad-preview='message']",
                "[data-ad-comet-preview='message']",
            ):
                try:
                    locator = article.locator(selector)

                    for index in range(min(locator.count(), 10)):
                        node = locator.nth(index)

                        try:
                            value = node.inner_text()
                            if value:
                                all_candidates.append(value)
                        except Exception:
                            pass

                        try:
                            value = node.text_content()
                            if value:
                                all_candidates.append(value)
                        except Exception:
                            pass
                except Exception:
                    pass

            try:
                blocks = article.locator("div[dir='auto']")
                for index in range(min(blocks.count(), 30)):
                    try:
                        value = blocks.nth(index).inner_text()
                        if value:
                            all_candidates.append(value)
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                article_text = article.inner_text()

                if article_text:
                    control_markers = (
                        "\nGefällt mir",
                        "\nKommentieren",
                        "\nTeilen",
                        "\nAlle Reaktionen",
                        "\nLike",
                        "\nComment",
                        "\nShare",
                    )

                    shortened_article_text = article_text
                    positions = [
                        shortened_article_text.find(marker)
                        for marker in control_markers
                        if marker in shortened_article_text
                    ]

                    if positions:
                        shortened_article_text = shortened_article_text[:min(positions)]

                    all_candidates.append(shortened_article_text)
            except Exception:
                pass

        for selector in (
            "meta[property='og:description']",
            "meta[name='twitter:description']",
            "meta[name='description']",
        ):
            try:
                value = page.locator(selector).first.get_attribute("content")
                if value:
                    all_candidates.append(value)
            except Exception:
                pass

        cleaned_candidates: list[str] = []

        for candidate in all_candidates:
            text = self._clean_candidate_text(candidate)

            if text and text not in cleaned_candidates:
                cleaned_candidates.append(text)

        if not cleaned_candidates:
            return ""

        complete_candidates = [
            text
            for text in cleaned_candidates
            if not self._looks_truncated(text)
        ]

        if complete_candidates:
            return max(complete_candidates, key=len)

        return max(cleaned_candidates, key=len)

    @staticmethod
    def _best_plausible_text(candidates: list[str]) -> str:
        cleaned: list[str] = []
        for candidate in candidates:
            text = FacebookImporter._clean_candidate_text(candidate)
            if text and text not in cleaned:
                cleaned.append(text)
        if not cleaned:
            return ""

        # Vollständige Varianten ohne abschließende Auslassung werden bevorzugt.
        complete = [text for text in cleaned if not FacebookImporter._looks_truncated(text)]
        return max(complete or cleaned, key=len)

    @staticmethod
    def _looks_truncated(text: str) -> bool:
        stripped = text.rstrip()
        return stripped.endswith(("...", "…", " um...", " um…"))

    @staticmethod
    def _clean_candidate_text(candidate: str) -> str:
        ignored = {
            "Gefällt mir", "Kommentieren", "Teilen", "Abspielen", "Pause",
            "Facebook", "Anmelden", "Neues Konto erstellen", "Mehr anzeigen",
            "Mehr ansehen", "See more",
        }
        text = " ".join(str(candidate).split()).strip()
        if not text or text in ignored or len(text) < 20:
            return ""

        # Ein eventuell mitkopierter Bedienhinweis gehört nicht zum Beitragstext.
        for marker in (" Mehr anzeigen", " Mehr ansehen", " See more"):
            if text.endswith(marker):
                text = text[:-len(marker)].rstrip()

        for suffix in (" | Facebook", " - Facebook"):
            if text.endswith(suffix):
                text = text[:-len(suffix)].strip()
        return text if len(text) >= 20 else ""

    @staticmethod
    def _first_plausible_text(candidates: list[str]) -> str:
        for candidate in candidates:
            text = FacebookImporter._clean_candidate_text(candidate)
            if text:
                return text
        return ""

    @staticmethod
    def _best_text(candidates: list[str]) -> str:
        ignored = {
            "Gefällt mir", "Kommentieren", "Teilen", "Abspielen", "Pause",
            "Facebook", "Anmelden", "Neues Konto erstellen",
        }
        cleaned: list[str] = []
        for candidate in candidates:
            text = " ".join(str(candidate).split()).strip()
            if not text or text in ignored or text in cleaned:
                continue
            if len(text) < 20:
                continue
            cleaned.append(text)

        if not cleaned:
            return ""

        # Lange Texte sind in der Regel die eigentliche Beitragsbeschreibung.
        return max(cleaned, key=len)

    def _preferred_video_page_url(self, page, *, fallback: str) -> str:
        candidates: list[str] = []
        try:
            links = page.locator("a[href*='/reel/']").evaluate_all(
                "links => links.map(link => link.href).filter(Boolean)"
            )
            candidates.extend(value for value in links if isinstance(value, str))
        except Exception:
            pass

        for candidate in candidates:
            normalized = self._normalize_external_url(candidate)
            if normalized:
                return normalized

        normalized_fallback = self._normalize_external_url(fallback)
        return normalized_fallback

    def _download_images(
        self,
        image_urls: list[str],
        *,
        cookies: dict[str, str],
        referer: str,
    ) -> list[str]:
        local_images: list[str] = []
        for image_url in image_urls:
            try:
                image_path = self.downloader.download_image(
                    image_url,
                    cookies=cookies,
                    referer=referer,
                )
                local_images.append(str(image_path))
            except Exception as error:
                print("Bild konnte nicht heruntergeladen werden:")
                print(image_url)
                print(error)
        return local_images

    @staticmethod
    def _cookies_as_dict(context) -> dict[str, str]:
        return {
            cookie["name"]: cookie["value"]
            for cookie in context.cookies()
        }

    @staticmethod
    def _clean_url(url: str) -> str:
        cleaned = url.strip()
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("Bitte einen vollständigen Facebook-Link mit https:// eingeben.")
        return cleaned

    @staticmethod
    def _normalize_external_url(url: str) -> str:
        cleaned = url.strip()
        if not cleaned:
            return ""
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Der Video-Link ist keine gültige Internetadresse.")
        if "facebook.com" not in parsed.netloc.lower() and "fb.watch" not in parsed.netloc.lower():
            raise ValueError("Bitte einen Facebook- oder fb.watch-Link als Video-Link verwenden.")
        return cleaned

    @staticmethod
    def _filter_post_images(image_urls: set[str]) -> list[str]:
        possible_post_images: list[str] = []
        for image_url in image_urls:
            url_lower = image_url.lower()
            if "scontent" not in url_lower:
                continue
            if "/t39.30808-1/" in url_lower:
                continue
            if "/t39.1997-6/" in url_lower:
                continue
            if "hads-ak" in url_lower:
                continue

            small_sizes = (
                "s16x16", "s24x24", "s32x32", "s40x40", "s48x48",
                "s60x60", "s80x80", "s100x100", "s110x80", "s120x120",
                "p16x16", "p24x24", "p32x32", "p40x40", "p48x48",
                "p80x80", "p120x120", "p240x240", "mx120x120",
                "mx240x240",
            )
            if any(size in url_lower for size in small_sizes):
                continue

            if "/t39.99422-6/" in url_lower:
                possible_post_images.append(image_url)
                continue

            large_image_markers = (
                "p526x296", "p720x720", "p960x960", "p1080x1080",
                "p1200x1200", "mx1200x1200", "mx2048x2048",
            )
            if any(marker in url_lower for marker in large_image_markers):
                possible_post_images.append(image_url)

        return sorted(possible_post_images)
