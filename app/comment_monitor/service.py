from __future__ import annotations

from datetime import datetime, timezone
import time

from app.models.facebook_comment import FacebookComment
from app.config import COMMENT_PAGE_TIMEOUT_SECONDS, COMMENT_REQUEST_TIMEOUT_SECONDS
from app.services.facebook_api import FacebookApiError, FacebookApiService
from app.services.meta_config_service import MetaConfigService
from app.services.settings_service import SettingsService
from app.comment_monitor.storage import CommentStorage
from app.comment_monitor.link_preview import (
    fetch_link_preview, first_http_url, is_facebook_media_permalink, is_facebook_url,
)


class CommentFetchCancelled(RuntimeError):
    """Interner Kontrollfluss für einen bewusst abgebrochenen Kommentarabruf."""


class CommentMonitorService:
    def __init__(self):
        self.settings_service = SettingsService()
        self.meta_config_service = MetaConfigService()
        self.storage = CommentStorage()

    @staticmethod
    def _field_list(raw: dict) -> str:
        if not isinstance(raw, dict):
            return "keine"
        fields = sorted(str(key) for key in raw.keys())
        return ", ".join(fields) if fields else "keine"


    @staticmethod
    def _attachment_info(raw: dict) -> tuple[str, str, str, str, str]:
        attachment = raw.get("attachment") if isinstance(raw.get("attachment"), dict) else {}
        if not attachment:
            return "", "", "", "", ""

        candidates = [attachment]
        subs = attachment.get("subattachments")
        if isinstance(subs, dict):
            data = subs.get("data")
            if isinstance(data, list):
                candidates.extend(item for item in data if isinstance(item, dict))

        atype = str(attachment.get("type", "") or "").strip()
        url = str(attachment.get("url", "") or "").strip()
        title = str(attachment.get("title", "") or attachment.get("description", "") or "").strip()
        image_url = ""

        for item in candidates:
            if not atype:
                atype = str(item.get("type", "") or "").strip()
            if not url:
                url = str(item.get("url", "") or "").strip()
            target = item.get("target") if isinstance(item.get("target"), dict) else {}
            if not url:
                url = str(target.get("url", "") or "").strip()
            if not title:
                title = str(item.get("title", "") or item.get("description", "") or "").strip()

            media = item.get("media") if isinstance(item.get("media"), dict) else {}
            image = media.get("image") if isinstance(media.get("image"), dict) else {}
            if not image_url:
                image_url = str(image.get("src", "") or "").strip()
            if not url:
                url = str(media.get("source", "") or "").strip()

        fields = ", ".join(sorted(str(key) for key in attachment.keys())) or "keine"
        diagnostic = f"Meta-Attachment vorhanden. Typ: {atype or 'nicht angegeben'}. Felder: {fields}."
        return atype, url, image_url, title, diagnostic

    def _enrich_external_link(
        self,
        *,
        message: str,
        attachment_type: str,
        attachment_url: str,
        attachment_image_url: str,
        attachment_title: str,
        attachment_diagnostic: str,
        permalink_url: str = "",
        existing_source: str = "",
    ) -> tuple[str, str, str, str, str, str]:
        """Ergänzt nur bei echten Link-Kommentaren eine externe OpenGraph-Vorschau.

        Priorität:
        1. Von Meta geliefertes Bild/Attachment.
        2. Erkennbarer Facebook-Foto-/Video-Permalink.
        3. Erst dann ein externer Link aus dem Kommentartext.

        Das verhindert, dass versteckte oder technisch mitgelieferte URLs aus
        ``message`` fälschlich als Kommentarbild dargestellt werden.
        """
        # Ein echtes Meta-Bild ist immer die beste Quelle.
        if attachment_image_url and existing_source not in {"comment_link"}:
            return (
                attachment_type, attachment_url, attachment_image_url,
                attachment_title, existing_source or "meta", attachment_diagnostic
            )

        # Ein Facebook-Medien-Permalink ist ein starkes Signal dafür, dass der
        # Kommentar selbst ein Foto/Video enthält. In diesem Fall darf niemals
        # ein externer Link aus dem message-Feld als Bildersatz verwendet werden.
        fb_media_url = ""
        for candidate in (attachment_url, permalink_url):
            if is_facebook_media_permalink(candidate):
                fb_media_url = candidate
                break
        if fb_media_url:
            diag = attachment_diagnostic or ""
            if diag:
                diag += " "
            diag += (
                "Facebook-Foto-/Medienlink erkannt. Externe OpenGraph-Vorschauen "
                "werden für diesen Kommentar bewusst nicht verwendet."
            )
            media_type = attachment_type
            if not media_type or media_type in {"link", "sticker_or_media"}:
                media_type = "facebook_media"
            # Falls zuvor eine falsche externe Vorschau gespeichert war, wird sie
            # bewusst verworfen. Der Facebook-Link bleibt als Originalreferenz.
            safe_title = "" if existing_source == "comment_link" else attachment_title
            return media_type, fb_media_url, "", safe_title, "facebook_media_permalink", diag

        # Wenn Meta selbst ein Attachment liefert (auch ohne Bild), respektieren wir
        # dieses und überschreiben es nicht mit irgendeinem message-Link.
        if attachment_type or attachment_url:
            source = existing_source or "meta"
            if source != "comment_link":
                return (
                    attachment_type, attachment_url, attachment_image_url,
                    attachment_title, source, attachment_diagnostic
                )

        link = first_http_url(message)
        if not link:
            return (
                attachment_type, attachment_url, attachment_image_url,
                attachment_title, existing_source or "", attachment_diagnostic,
            )

        # Facebook-Links werden nie per OpenGraph als externe Vorschau behandelt.
        if is_facebook_url(link):
            diag = attachment_diagnostic or ""
            if diag:
                diag += " "
            diag += "Facebook-Link im Kommentar erkannt; keine externe OpenGraph-Vorschau erzeugt."
            return attachment_type or "facebook_link", attachment_url or link, "", attachment_title, "facebook_link", diag

        preview = fetch_link_preview(link)
        if not preview:
            diag = attachment_diagnostic or ""
            if diag:
                diag += " "
            diag += "Im Kommentar wurde ein externer Link erkannt, aber keine öffentliche Bildvorschau konnte geladen werden."
            return (
                attachment_type or "link", attachment_url or link, "",
                attachment_title, "comment_link", diag
            )

        diag = attachment_diagnostic or ""
        if diag:
            diag += " "
        diag += "Linkvorschau aus den öffentlichen OpenGraph-Metadaten der ausdrücklich verlinkten Seite ergänzt."
        return (
            attachment_type or "link",
            attachment_url or preview.get("url", "") or link,
            preview.get("image_url", ""),
            attachment_title or preview.get("title", ""),
            "comment_link",
            diag,
        )

    def _resolve_author_for_new_comment(
        self,
        *,
        api: FacebookApiService,
        raw: dict,
        comment_id: str,
        page_access_token: str,
        request_timeout: float = 30,
    ) -> tuple[dict, str, str, dict]:
        """Ermittelt den Autor eines neu gefundenen Kommentars.

        Zuerst wird ``from`` aus der Comments-Edge verwendet. Fehlt es, folgt
        genau eine direkte Abfrage des einzelnen Kommentarobjekts. So können
        wir unterscheiden, ob unser Parser den Autor verliert oder Meta ihn
        tatsächlich nicht ausliefert.
        """
        edge_author = raw.get("from") if isinstance(raw.get("from"), dict) else {}
        if edge_author.get("id") or edge_author.get("name"):
            return (
                edge_author,
                "comments_edge",
                "Comments-Edge lieferte from{id,name}. "
                f"Felder: {self._field_list(raw)}",
                {},
            )

        edge_fields = self._field_list(raw)
        try:
            direct = api.get_comment_details(
                comment_id=comment_id,
                page_access_token=page_access_token,
                request_timeout=request_timeout,
            )
        except FacebookApiError as error:
            return (
                {},
                "not_available",
                "Comments-Edge ohne from. "
                f"Edge-Felder: {edge_fields}. "
                f"Direktabfrage fehlgeschlagen: {error}",
                {},
            )

        direct_author = (
            direct.get("from")
            if isinstance(direct.get("from"), dict)
            else {}
        )
        direct_fields = self._field_list(direct)
        if direct_author.get("id") or direct_author.get("name"):
            return (
                direct_author,
                "direct_comment",
                "Comments-Edge ohne from; direkte Kommentarabfrage lieferte "
                "from{id,name}. "
                f"Edge-Felder: {edge_fields}. Direkt-Felder: {direct_fields}",
                direct,
            )

        return (
            {},
            "not_available",
            "Meta hat den Autor weder über die Comments-Edge noch über die "
            "direkte Kommentarabfrage geliefert. "
            f"Edge-Felder: {edge_fields}. Direkt-Felder: {direct_fields}",
            direct,
        )

    def fetch_all(
        self,
        post_limit: int = 25,
        comment_limit: int = 100,
        should_cancel=None,
        progress_callback=None,
        page_timeout_seconds: int = COMMENT_PAGE_TIMEOUT_SECONDS,
        request_timeout_seconds: int = COMMENT_REQUEST_TIMEOUT_SECONDS,
    ) -> dict:
        pages = [page for page in self.settings_service.load_pages() if page.is_active]
        existing = {comment.comment_id: comment for comment in self.storage.load()}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        result = {
            "page_count": len(pages),
            "pages": [],
            "new_count": 0,
            "seen_count": 0,
            "error_count": 0,
        }

        config = self.meta_config_service.load()
        api = FacebookApiService(config=config)

        def check_cancel() -> None:
            if should_cancel is not None and should_cancel():
                raise CommentFetchCancelled("Kommentarabruf wurde abgebrochen.")

        def update_progress(page_index: int, page_name: str, stage: str = "") -> None:
            if progress_callback is not None:
                progress_callback({
                    "page_index": page_index,
                    "page_count": len(pages),
                    "page_name": page_name,
                    "stage": stage,
                    "new_count": result["new_count"],
                    "seen_count": result["seen_count"],
                    "error_count": result["error_count"],
                    "pages": result["pages"],
                })

        for page_index, page in enumerate(pages, start=1):
            check_cancel()
            page_started = time.monotonic()
            page_deadline = page_started + max(30, int(page_timeout_seconds))
            update_progress(page_index, page.name, "Seite wird geöffnet")
            page_result = {
                "page_id": page.page_id,
                "page_name": page.name,
                "posts": 0,
                "comments": 0,
                "new": 0,
                "error": "",
            }
            result["pages"].append(page_result)
            author_direct_unavailable = False

            if not page.access_token:
                page_result["error"] = "Für diese Seite ist kein Seitenzugriffstoken gespeichert."
                result["error_count"] += 1
                update_progress(page_index, page.name, "Übersprungen: kein Zugriffstoken")
                continue

            try:
                check_cancel()
                posts = api.get_page_published_posts(
                    page_id=page.page_id,
                    page_access_token=page.access_token,
                    limit=post_limit,
                    request_timeout=request_timeout_seconds,
                )
                page_result["posts"] = len(posts)

                update_progress(page_index, page.name, f"{len(posts)} Beiträge gefunden")

                for post_number, post in enumerate(posts, start=1):
                    check_cancel()
                    if time.monotonic() >= page_deadline:
                        raise TimeoutError(
                            f"Zeitlimit von {page_timeout_seconds} Sekunden für diese Seite erreicht. "
                            "Die Seite wurde übersprungen, der Abruf läuft mit der nächsten Seite weiter."
                        )
                    post_id = str(post.get("id", "")).strip()
                    if not post_id:
                        continue

                    comments = api.get_post_comments(
                        post_id=post_id,
                        page_access_token=page.access_token,
                        limit=comment_limit,
                        request_timeout=min(request_timeout_seconds, max(5, int(page_deadline - time.monotonic()))),
                    )
                    page_result["comments"] += len(comments)
                    result["seen_count"] += len(comments)

                    update_progress(page_index, page.name, f"Beitrag {post_number}/{len(posts)} · {page_result['comments']} Kommentare")

                    for raw in comments:
                        check_cancel()
                        if time.monotonic() >= page_deadline:
                            raise TimeoutError(
                                f"Zeitlimit von {page_timeout_seconds} Sekunden für diese Seite erreicht. "
                                "Die Seite wurde übersprungen, der Abruf läuft mit der nächsten Seite weiter."
                            )
                        comment_id = str(raw.get("id", "")).strip()
                        if not comment_id:
                            continue

                        edge_author = raw.get("from") if isinstance(raw.get("from"), dict) else {}
                        parent = raw.get("parent") if isinstance(raw.get("parent"), dict) else {}
                        (
                            attachment_type, attachment_url, attachment_image_url,
                            attachment_title, attachment_diagnostic
                        ) = self._attachment_info(raw)
                        attachment_source = "meta" if (attachment_type or attachment_url or attachment_image_url) else ""
                        is_hidden = bool(raw.get("is_hidden", False))

                        current = existing.get(comment_id)
                        author = edge_author
                        author_source = ""
                        author_diagnostic = ""
                        direct_raw: dict = {}

                        if current is None:
                            if (edge_author.get("id") or edge_author.get("name")) or not author_direct_unavailable:
                                author, author_source, author_diagnostic, direct_raw = self._resolve_author_for_new_comment(
                                    api=api,
                                    raw=raw,
                                    comment_id=comment_id,
                                    page_access_token=page.access_token,
                                    request_timeout=min(request_timeout_seconds, max(5, int(page_deadline - time.monotonic()))),
                                )
                                # Liefert Meta bei der ersten erfolgreichen Direktabfrage dieser
                                # Seite ebenfalls kein from-Feld, sparen wir uns dieselbe erfolglose
                                # Diagnose für alle weiteren neuen Kommentare dieser Seite.
                                if (not edge_author.get("id") and not edge_author.get("name")
                                        and author_source == "not_available" and direct_raw):
                                    author_direct_unavailable = True
                            else:
                                author = {}
                                author_source = "not_available"
                                author_diagnostic = (
                                    "Meta hat auf dieser Seite bei einer vorherigen Direktabfrage kein "
                                    "from{id,name} geliefert; weitere redundante Autorabfragen wurden "
                                    "für diesen Abruf übersprungen."
                                )
                                direct_raw = {}
                            if not (attachment_type or attachment_url or attachment_image_url):
                                (
                                    direct_type, direct_url, direct_image, direct_title, direct_diag
                                ) = self._attachment_info(direct_raw)
                                attachment_type = direct_type or attachment_type
                                attachment_url = direct_url or attachment_url
                                attachment_image_url = direct_image or attachment_image_url
                                attachment_title = direct_title or attachment_title
                                attachment_diagnostic = direct_diag or attachment_diagnostic
                                if direct_type or direct_url or direct_image:
                                    attachment_source = "meta_direct"

                            message = str(raw.get("message", "") or direct_raw.get("message", "") or "")
                            (
                                attachment_type, attachment_url, attachment_image_url,
                                attachment_title, enriched_source, attachment_diagnostic
                            ) = self._enrich_external_link(
                                message=message,
                                permalink_url=str(raw.get("permalink_url", "") or direct_raw.get("permalink_url", "") or ""),
                                attachment_type=attachment_type,
                                attachment_url=attachment_url,
                                attachment_image_url=attachment_image_url,
                                attachment_title=attachment_title,
                                attachment_diagnostic=attachment_diagnostic,
                                existing_source=attachment_source,
                            )
                            attachment_source = enriched_source or attachment_source
                            if not message and not (attachment_type or attachment_url or attachment_image_url):
                                attachment_type = "sticker_or_media"
                                attachment_source = "meta_missing_preview"
                                attachment_diagnostic = (
                                    "Kommentar enthält keinen Text. Meta liefert für diesen Kommentar weder "
                                    "Attachment noch Vorschaubild; er wird daher als unkritischer Sticker-/"
                                    "Medienkommentar behandelt."
                                )

                            current = FacebookComment(
                                comment_id=comment_id,
                                page_id=page.page_id,
                                page_name=page.name,
                                post_id=post_id,
                                post_message=str(post.get("message", "") or ""),
                                post_permalink=str(post.get("permalink_url", "") or ""),
                                author_id=str(author.get("id", "") or ""),
                                author_name=str(author.get("name", "") or raw.get("username", "") or ""),
                                author_lookup_source=author_source,
                                author_diagnostic=author_diagnostic,
                                message=message,
                                created_time=str(raw.get("created_time", "") or ""),
                                permalink_url=str(raw.get("permalink_url", "") or ""),
                                parent_id=str(parent.get("id", "") or ""),
                                attachment_type=attachment_type,
                                attachment_url=attachment_url,
                                attachment_image_url=attachment_image_url,
                                attachment_title=attachment_title,
                                attachment_source=attachment_source,
                                attachment_diagnostic=attachment_diagnostic,
                                is_hidden=is_hidden,
                                can_hide=bool(raw.get("can_hide", False)),
                                can_remove=bool(raw.get("can_remove", False)),
                                status="hidden" if is_hidden else "new",
                                fetched_at=now,
                                last_seen_at=now,
                            )
                            existing[comment_id] = current
                            page_result["new"] += 1
                            result["new_count"] += 1
                        else:
                            current.page_id = page.page_id
                            current.page_name = page.name
                            current.post_id = post_id
                            current.post_message = str(post.get("message", "") or current.post_message)
                            current.post_permalink = str(post.get("permalink_url", "") or current.post_permalink)
                            current.author_id = str(edge_author.get("id", "") or current.author_id)
                            current.author_name = str(edge_author.get("name", "") or raw.get("username", "") or current.author_name or "")
                            if edge_author.get("id") or edge_author.get("name"):
                                current.author_lookup_source = "comments_edge"
                                current.author_diagnostic = (
                                    "Comments-Edge lieferte from{id,name}. "
                                    f"Felder: {self._field_list(raw)}"
                                )
                            current.message = str(raw.get("message", "") or current.message)
                            current.created_time = str(raw.get("created_time", "") or current.created_time)
                            current.permalink_url = str(raw.get("permalink_url", "") or current.permalink_url)
                            current.parent_id = str(parent.get("id", "") or current.parent_id)

                            # Bereits bekannte Kommentare werden im normalen Abruf nicht mehr
                            # einzeln über /{comment_id} nachgeladen. Das verursachte bei vielen
                            # Textkommentaren hunderte zusätzliche Meta-Aufrufe. Für gezieltes
                            # Nachladen alter Medieninfos gibt es den separaten Refresh-Job.

                            message_for_preview = str(raw.get("message", "") or current.message or "")
                            (
                                attachment_type, attachment_url, attachment_image_url,
                                attachment_title, enriched_source, attachment_diagnostic
                            ) = self._enrich_external_link(
                                message=message_for_preview,
                                permalink_url=str(raw.get("permalink_url", "") or current.permalink_url or ""),
                                attachment_type=attachment_type or current.attachment_type,
                                attachment_url=attachment_url or current.attachment_url,
                                attachment_image_url=attachment_image_url or current.attachment_image_url,
                                attachment_title=attachment_title or current.attachment_title,
                                attachment_diagnostic=attachment_diagnostic or current.attachment_diagnostic,
                                existing_source=attachment_source or current.attachment_source,
                            )
                            attachment_source = enriched_source or attachment_source or current.attachment_source

                            # War in einer älteren Version eine externe OpenGraph-Vorschau
                            # gespeichert, wird sie bei erkanntem Facebook-Medienlink bewusst
                            # entfernt. Lieber kein Vorschaubild als ein falsches.
                            if attachment_source == "facebook_media_permalink":
                                current.attachment_image_url = ""
                                if current.attachment_source == "comment_link":
                                    current.attachment_title = ""

                            if not message_for_preview and not (attachment_type or attachment_url or attachment_image_url):
                                attachment_type = "sticker_or_media"
                                attachment_source = "meta_missing_preview"
                                attachment_diagnostic = (
                                    "Kommentar enthält keinen Text. Meta liefert für diesen Kommentar weder "
                                    "Attachment noch Vorschaubild; er wird daher als unkritischer Sticker-/"
                                    "Medienkommentar behandelt."
                                )

                            current.attachment_type = attachment_type or current.attachment_type
                            current.attachment_url = attachment_url or current.attachment_url
                            current.attachment_image_url = attachment_image_url or current.attachment_image_url
                            current.attachment_title = attachment_title or current.attachment_title
                            current.attachment_source = attachment_source or current.attachment_source
                            current.attachment_diagnostic = attachment_diagnostic or current.attachment_diagnostic
                            current.is_hidden = is_hidden
                            current.can_hide = bool(raw.get("can_hide", current.can_hide))
                            current.can_remove = bool(raw.get("can_remove", current.can_remove))
                            current.last_seen_at = now
                            if current.status != "deleted":
                                if is_hidden:
                                    current.status = "hidden"
                                elif current.status != "handled":
                                    current.status = "new"

            except (FacebookApiError, TimeoutError) as error:
                page_result["error"] = str(error)
                result["error_count"] += 1
            finally:
                # Zwischenspeichern pro Seite: bei Abbruch/Restart geht die bisherige Arbeit nicht verloren.
                comments_snapshot = list(existing.values())
                comments_snapshot.sort(key=lambda item: item.created_time or item.fetched_at, reverse=True)
                self.storage.save(comments_snapshot)
                update_progress(page_index, page.name, "Seite abgeschlossen")

        comments = list(existing.values())
        comments.sort(key=lambda item: item.created_time or item.fetched_at, reverse=True)
        self.storage.save(comments)
        return result

    def refresh_existing(self, progress_callback=None) -> dict:
        """Aktualisiert bereits gespeicherte Kommentare direkt über ihre Comment-ID.

        Dieser Lauf ist bewusst unabhängig von den letzten 25 Seitenbeiträgen. Er
        ergänzt insbesondere Medien-/Linkvorschauen und – falls Meta sie später
        doch liefert – Autorinformationen, ohne neue Kommentar-Datensätze anzulegen.
        """
        comments = [item for item in self.storage.load() if item.status != "deleted"]
        pages = {page.page_id: page for page in self.settings_service.load_pages() if page.is_active}
        api = FacebookApiService(config=self.meta_config_service.load())
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        result = {
            "total": len(comments),
            "processed": 0,
            "updated": 0,
            "media_found": 0,
            "preview_found": 0,
            "author_found": 0,
            "errors": 0,
            "last_error": "",
        }

        def emit():
            if progress_callback:
                progress_callback(dict(result))

        for index, current in enumerate(comments, start=1):
            changed = False
            page = pages.get(current.page_id)
            if page is None or not page.access_token:
                current.media_refresh_error = "Kein aktives Seitenzugriffstoken vorhanden."
                result["errors"] += 1
                result["last_error"] = current.media_refresh_error
                result["processed"] = index
                emit()
                continue

            try:
                direct = api.get_comment_details(
                    comment_id=current.comment_id,
                    page_access_token=page.access_token,
                )

                direct_author = direct.get("from") if isinstance(direct.get("from"), dict) else {}
                if (direct_author.get("id") or direct_author.get("name")) and not (current.author_id and current.author_name):
                    current.author_id = str(direct_author.get("id", "") or current.author_id)
                    current.author_name = str(direct_author.get("name", "") or current.author_name)
                    current.author_lookup_source = "direct_comment_refresh"
                    current.author_diagnostic = (
                        "Bestehender Kommentar wurde direkt aktualisiert; Meta lieferte from{id,name}. "
                        f"Felder: {self._field_list(direct)}"
                    )
                    result["author_found"] += 1
                    changed = True

                if direct.get("message") and not current.message:
                    current.message = str(direct.get("message") or "")
                    changed = True
                if direct.get("permalink_url") and not current.permalink_url:
                    current.permalink_url = str(direct.get("permalink_url") or "")
                    changed = True

                atype, aurl, aimage, atitle, adiag = self._attachment_info(direct)
                source = "meta_direct_refresh" if (atype or aurl or aimage) else current.attachment_source

                before_image = current.attachment_image_url
                before_any = bool(current.attachment_type or current.attachment_url or current.attachment_image_url)

                (
                    atype, aurl, aimage, atitle, enriched_source, adiag
                ) = self._enrich_external_link(
                    message=current.message or str(direct.get("message", "") or ""),
                    permalink_url=str(direct.get("permalink_url", "") or current.permalink_url or ""),
                    attachment_type=atype or ("" if current.attachment_type == "sticker_or_media" else current.attachment_type),
                    attachment_url=aurl or current.attachment_url,
                    attachment_image_url=aimage or current.attachment_image_url,
                    attachment_title=atitle or current.attachment_title,
                    attachment_diagnostic=adiag or current.attachment_diagnostic,
                    existing_source=("meta_direct_refresh" if (atype or aurl or aimage) else current.attachment_source),
                )
                source = enriched_source or source

                if source == "facebook_media_permalink":
                    # Falsche externe Vorschaubilder aus 2.8.3/2.8.4 aktiv entfernen.
                    if current.attachment_image_url:
                        current.attachment_image_url = ""
                        changed = True
                    if current.attachment_source == "comment_link" and current.attachment_title:
                        current.attachment_title = ""
                        changed = True

                if atype or aurl or aimage:
                    if not before_any:
                        result["media_found"] += 1
                    if aimage and not before_image:
                        result["preview_found"] += 1
                    if atype and atype != current.attachment_type:
                        current.attachment_type = atype
                        changed = True
                    if aurl and aurl != current.attachment_url:
                        current.attachment_url = aurl
                        changed = True
                    if aimage and aimage != current.attachment_image_url:
                        current.attachment_image_url = aimage
                        changed = True
                    if atitle and atitle != current.attachment_title:
                        current.attachment_title = atitle
                        changed = True
                    if source and source != current.attachment_source:
                        current.attachment_source = source
                        changed = True
                    if adiag and adiag != current.attachment_diagnostic:
                        current.attachment_diagnostic = adiag
                        changed = True
                elif not (current.message or "").strip():
                    # Sticker/Avatar ohne von Meta gelieferte Vorschau bleibt bewusst unkritisch.
                    if current.attachment_type != "sticker_or_media":
                        current.attachment_type = "sticker_or_media"
                        changed = True
                    current.attachment_source = current.attachment_source or "meta_missing_preview"
                    current.attachment_diagnostic = (
                        "Bestehender Kommentar direkt nachgeladen. Meta liefert weiterhin weder "
                        "Attachment noch Vorschaubild; Behandlung als unkritischer Sticker-/Medienkommentar."
                    )

                current.media_refreshed_at = now
                current.media_refresh_error = ""
                if changed:
                    result["updated"] += 1

            except FacebookApiError as error:
                current.media_refreshed_at = now
                current.media_refresh_error = str(error)
                result["errors"] += 1
                result["last_error"] = str(error)

            result["processed"] = index

            # Regelmäßig persistieren, damit ein langer Lauf nach einem Neustart
            # nicht vollständig verloren ist.
            if index % 25 == 0 or index == len(comments):
                self.storage.save(comments)
                emit()

        self.storage.save(comments)
        emit()
        return result

    def _page_token(self, page_id: str) -> str:
        page = next(
            (item for item in self.settings_service.load_pages() if item.page_id == page_id),
            None,
        )
        if page is None or not page.access_token:
            raise FacebookApiError("Für diese Facebook-Seite ist kein Zugriffstoken gespeichert.")
        return page.access_token

    def set_hidden(self, comment_id: str, hidden: bool) -> FacebookComment:
        comment = self.storage.get(comment_id)
        if comment is None:
            raise FacebookApiError("Der Kommentar wurde im Monitor nicht gefunden.")
        token = self._page_token(comment.page_id)
        api = FacebookApiService(config=self.meta_config_service.load())
        api.set_comment_hidden(comment_id=comment.comment_id, page_access_token=token, hidden=hidden)
        comment.is_hidden = hidden
        comment.status = "hidden" if hidden else "new"
        self.storage.update(comment)
        return comment

    def delete(self, comment_id: str) -> FacebookComment:
        comment = self.storage.get(comment_id)
        if comment is None:
            raise FacebookApiError("Der Kommentar wurde im Monitor nicht gefunden.")
        token = self._page_token(comment.page_id)
        api = FacebookApiService(config=self.meta_config_service.load())
        api.delete_comment(comment_id=comment.comment_id, page_access_token=token)
        comment.status = "deleted"
        self.storage.update(comment)
        return comment

    def set_handled(self, comment_id: str, handled: bool) -> FacebookComment:
        comment = self.storage.get(comment_id)
        if comment is None:
            raise FacebookApiError("Der Kommentar wurde im Monitor nicht gefunden.")
        if comment.status == "deleted":
            return comment
        comment.status = "handled" if handled else ("hidden" if comment.is_hidden else "new")
        self.storage.update(comment)
        return comment

    def generate_reply_suggestion(self, comment_id: str) -> FacebookComment:
        from app.comment_monitor.ai import CommentAiError, suggest_reply

        comment = self.storage.get(comment_id)
        if comment is None:
            raise FacebookApiError("Der Kommentar wurde im Monitor nicht gefunden.")

        comment.reply_status = "running"
        comment.reply_error = ""
        self.storage.update(comment)
        try:
            suggestion = suggest_reply({
                "page": comment.page_name,
                "post": comment.post_message,
                "comment": comment.message,
                "category": comment.ai_category,
                "priority": comment.ai_priority,
                "recommendation": comment.ai_recommendation,
            })
            comment.reply_suggestion = suggestion.get("reply", "")
            comment.reply_style = suggestion.get("style", "")
            comment.reply_status = "ready"
            comment.reply_error = ""
        except CommentAiError as error:
            comment.reply_status = "error"
            comment.reply_error = str(error)
        self.storage.update(comment)
        return comment

    def set_user_blocked_on_known_pages(self, user_key: str, blocked: bool = True) -> dict:
        """Blockiert/entsperrt einen gebündelten Kommentator auf allen eindeutig bekannten Seiten.

        Facebook verwendet Page-Scoped User IDs. Deshalb wird pro Seite ausschließlich die
        dort tatsächlich beobachtete PSID verwendet. Seiten mit mehrdeutiger Namenszuordnung
        werden nicht automatisch verändert.
        """
        from app.comment_monitor.users import CommentUserStateStorage, get_user_profile
        from app.models.facebook_comment_user import FacebookCommentUserState

        comments = self.storage.load()
        profile = get_user_profile(comments, user_key)
        if profile is None:
            raise FacebookApiError("Das Benutzerprofil wurde nicht gefunden.")
        if not profile.get("page_ids"):
            raise FacebookApiError("Für diesen Benutzer ist auf keiner Seite eine eindeutige Facebook-ID gespeichert.")

        pages = {page.page_id: page for page in self.settings_service.load_pages() if page.is_active}
        api = FacebookApiService(config=self.meta_config_service.load())
        results = []
        success_count = 0
        error_count = 0

        for page_id, psid in profile.get("page_ids", {}).items():
            page = pages.get(page_id)
            page_name = page.name if page else page_id
            if page is None or not page.access_token:
                results.append({"page_id": page_id, "page_name": page_name, "success": False, "error": "Kein Seitenzugriffstoken gespeichert."})
                error_count += 1
                continue
            try:
                api.set_page_user_blocked(
                    page_id=page_id,
                    page_access_token=page.access_token,
                    user_id=psid,
                    blocked=blocked,
                )
                results.append({"page_id": page_id, "page_name": page_name, "success": True, "error": ""})
                success_count += 1
            except FacebookApiError as error:
                results.append({"page_id": page_id, "page_name": page_name, "success": False, "error": str(error)})
                error_count += 1

        state_storage = CommentUserStateStorage()
        state = state_storage.get(user_key) or FacebookCommentUserState(
            user_key=user_key,
            display_name=str(profile.get("display_name", "")),
        )
        state.status = "blocked" if blocked and success_count else ("normal" if not blocked and success_count else state.status)
        state.last_action = "blocked" if blocked else "unblocked"
        state.last_action_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for item in results:
            if item["success"]:
                state.page_block_status[item["page_id"]] = "blocked" if blocked else "unblocked"
            else:
                state.page_block_status[item["page_id"]] = "error: " + item["error"]
        state_storage.update(state)

        return {
            "success_count": success_count,
            "error_count": error_count,
            "results": results,
            "blocked": blocked,
            "display_name": profile.get("display_name", ""),
        }

    def set_user_watchlist(self, user_key: str, enabled: bool = True) -> None:
        from app.comment_monitor.users import CommentUserStateStorage, get_user_profile
        from app.models.facebook_comment_user import FacebookCommentUserState

        profile = get_user_profile(self.storage.load(), user_key)
        if profile is None:
            raise FacebookApiError("Das Benutzerprofil wurde nicht gefunden.")
        state_storage = CommentUserStateStorage()
        state = state_storage.get(user_key) or FacebookCommentUserState(
            user_key=user_key,
            display_name=str(profile.get("display_name", "")),
        )
        state.status = "watchlist" if enabled else "normal"
        state.last_action = "watchlist_on" if enabled else "watchlist_off"
        state.last_action_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        state_storage.update(state)
