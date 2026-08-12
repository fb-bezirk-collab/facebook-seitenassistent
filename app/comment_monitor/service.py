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

                        author = raw.get("from") if isinstance(raw.get("from"), dict) else {}
                        parent = raw.get("parent") if isinstance(raw.get("parent"), dict) else {}
                        is_hidden = bool(raw.get("is_hidden", False))

                        current = existing.get(comment_id)
                        if current is None:
                            current = FacebookComment(
                                comment_id=comment_id,
                                page_id=page.page_id,
                                page_name=page.name,
                                post_id=post_id,
                                post_message=str(post.get("message", "") or ""),
                                post_permalink=str(post.get("permalink_url", "") or ""),
                                author_id=str(author.get("id", "") or ""),
                                author_name=str(author.get("name", "") or "Unbekannt"),
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
                            current.author_id = str(author.get("id", "") or current.author_id)
                            current.author_name = str(author.get("name", "") or current.author_name or "Unbekannt")
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
