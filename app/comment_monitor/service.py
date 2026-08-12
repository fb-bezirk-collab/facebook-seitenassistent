from __future__ import annotations

from datetime import datetime, timezone

from app.models.facebook_comment import FacebookComment
from app.services.facebook_api import FacebookApiError, FacebookApiService
from app.services.meta_config_service import MetaConfigService
from app.services.settings_service import SettingsService
from app.comment_monitor.storage import CommentStorage


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

    def _resolve_author_for_new_comment(
        self,
        *,
        api: FacebookApiService,
        raw: dict,
        comment_id: str,
        page_access_token: str,
    ) -> tuple[dict, str, str]:
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
            )

        edge_fields = self._field_list(raw)
        try:
            direct = api.get_comment_details(
                comment_id=comment_id,
                page_access_token=page_access_token,
            )
        except FacebookApiError as error:
            return (
                {},
                "not_available",
                "Comments-Edge ohne from. "
                f"Edge-Felder: {edge_fields}. "
                f"Direktabfrage fehlgeschlagen: {error}",
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
            )

        return (
            {},
            "not_available",
            "Meta hat den Autor weder über die Comments-Edge noch über die "
            "direkte Kommentarabfrage geliefert. "
            f"Edge-Felder: {edge_fields}. Direkt-Felder: {direct_fields}",
        )

    def fetch_all(self, post_limit: int = 25, comment_limit: int = 100) -> dict:
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

        for page in pages:
            page_result = {
                "page_id": page.page_id,
                "page_name": page.name,
                "posts": 0,
                "comments": 0,
                "new": 0,
                "error": "",
            }
            result["pages"].append(page_result)

            if not page.access_token:
                page_result["error"] = "Für diese Seite ist kein Seitenzugriffstoken gespeichert."
                result["error_count"] += 1
                continue

            try:
                posts = api.get_page_published_posts(
                    page_id=page.page_id,
                    page_access_token=page.access_token,
                    limit=post_limit,
                )
                page_result["posts"] = len(posts)

                for post in posts:
                    post_id = str(post.get("id", "")).strip()
                    if not post_id:
                        continue

                    comments = api.get_post_comments(
                        post_id=post_id,
                        page_access_token=page.access_token,
                        limit=comment_limit,
                    )
                    page_result["comments"] += len(comments)
                    result["seen_count"] += len(comments)

                    for raw in comments:
                        comment_id = str(raw.get("id", "")).strip()
                        if not comment_id:
                            continue

                        edge_author = raw.get("from") if isinstance(raw.get("from"), dict) else {}
                        parent = raw.get("parent") if isinstance(raw.get("parent"), dict) else {}
                        is_hidden = bool(raw.get("is_hidden", False))

                        current = existing.get(comment_id)
                        author = edge_author
                        author_source = ""
                        author_diagnostic = ""

                        if current is None:
                            author, author_source, author_diagnostic = self._resolve_author_for_new_comment(
                                api=api,
                                raw=raw,
                                comment_id=comment_id,
                                page_access_token=page.access_token,
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
                                message=str(raw.get("message", "") or ""),
                                created_time=str(raw.get("created_time", "") or ""),
                                permalink_url=str(raw.get("permalink_url", "") or ""),
                                parent_id=str(parent.get("id", "") or ""),
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
                            current.is_hidden = is_hidden
                            current.can_hide = bool(raw.get("can_hide", current.can_hide))
                            current.can_remove = bool(raw.get("can_remove", current.can_remove))
                            current.last_seen_at = now
                            if current.status != "deleted":
                                if is_hidden:
                                    current.status = "hidden"
                                elif current.status != "handled":
                                    current.status = "new"

            except FacebookApiError as error:
                page_result["error"] = str(error)
                result["error_count"] += 1

        comments = list(existing.values())
        comments.sort(key=lambda item: item.created_time or item.fetched_at, reverse=True)
        self.storage.save(comments)
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
