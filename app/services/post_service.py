import json
from pathlib import Path
from uuid import uuid4

from app.config import POSTS_FILE
from app.models.managed_post import ManagedPost, utc_now_iso


class PostService:
    def __init__(self, posts_file: Path = POSTS_FILE):
        self.posts_file = posts_file
        self._ensure_file_exists()

    def list_posts(self, status: str | None = None) -> list[ManagedPost]:
        posts = self._load_all()

        if status:
            posts = [post for post in posts if post.status == status]

        return sorted(
            posts,
            key=lambda post: post.updated_at,
            reverse=True,
        )

    def get_post(self, post_id: str) -> ManagedPost | None:
        return next(
            (post for post in self._load_all() if post.id == post_id),
            None,
        )

    def create_draft(
        self,
        *,
        title: str,
        text: str,
        text_variants: list[dict[str, str]],
        images: list[str],
        videos: list[str],
        video_url: str = "",
        page_id: str = "",
        source_url: str = "",
        source_type: str = "",
        source_name: str = "",
        source_item_id: str = "",
        source_meta: dict | None = None,
    ) -> ManagedPost:
        now = utc_now_iso()

        draft = ManagedPost(
            id=str(uuid4()),
            title=self._clean_title(title, text),
            text=text.strip(),
            text_variants=self._clean_text_variants(text_variants),
            images=self._clean_media(images),
            videos=self._clean_media(videos),
            video_url=video_url.strip(),
            page_id=page_id.strip(),
            source_url=source_url.strip(),
            source_type=source_type.strip(),
            source_name=source_name.strip(),
            source_item_id=source_item_id.strip(),
            source_meta=source_meta if isinstance(source_meta, dict) else {},
            status="draft",
            created_at=now,
            updated_at=now,
        )

        posts = self._load_all()
        posts.append(draft)
        self._save_all(posts)
        return draft

    def update_draft(
        self,
        post_id: str,
        *,
        title: str,
        text: str,
        text_variants: list[dict[str, str]],
        images: list[str],
        videos: list[str],
        video_url: str = "",
        page_id: str = "",
        source_url: str = "",
    ) -> ManagedPost | None:
        posts = self._load_all()

        for post in posts:
            if post.id != post_id:
                continue
            if post.status != "draft":
                return None

            post.title = self._clean_title(title, text)
            post.text = text.strip()
            post.text_variants = self._clean_text_variants(text_variants)
            post.images = self._clean_media(images)
            post.videos = self._clean_media(videos)
            post.video_url = video_url.strip()
            post.page_id = page_id.strip()
            post.source_url = source_url.strip()
            post.updated_at = utc_now_iso()

            self._save_all(posts)
            return post

        return None

    def mark_published(self, post_id: str) -> ManagedPost | None:
        posts = self._load_all()

        for post in posts:
            if post.id != post_id:
                continue

            post.status = "published"
            post.published_at = utc_now_iso()
            post.error_message = ""
            post.updated_at = utc_now_iso()
            self._save_all(posts)
            return post

        return None

    def delete_draft(self, post_id: str) -> bool:
        posts = self._load_all()
        remaining = [
            post
            for post in posts
            if not (post.id == post_id and post.status == "draft")
        ]

        if len(remaining) == len(posts):
            return False

        self._save_all(remaining)
        return True

    def _ensure_file_exists(self) -> None:
        self.posts_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.posts_file.exists():
            self._save_all([])

    def _load_all(self) -> list[ManagedPost]:
        try:
            content = self.posts_file.read_text(encoding="utf-8").strip()
            raw_data = json.loads(content) if content else []
        except (OSError, json.JSONDecodeError):
            return []

        if not isinstance(raw_data, list):
            return []

        posts: list[ManagedPost] = []

        for item in raw_data:
            if not isinstance(item, dict):
                continue

            post = ManagedPost.from_dict(item)
            if post.id:
                posts.append(post)

        return posts

    def _save_all(self, posts: list[ManagedPost]) -> None:
        temporary_file = self.posts_file.with_suffix(".tmp")
        temporary_file.write_text(
            json.dumps(
                [post.to_dict() for post in posts],
                ensure_ascii=False,
                indent=4,
            ),
            encoding="utf-8",
        )
        temporary_file.replace(self.posts_file)

    @staticmethod
    def _clean_text_variants(
        variants: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        cleaned: list[dict[str, str]] = []

        for index, item in enumerate(variants[:8], start=1):
            if not isinstance(item, dict):
                continue

            text = str(item.get("text", "")).strip()
            if not text:
                continue

            title = (
                str(item.get("title", "")).strip()
                or f"Variante {index}"
            )

            cleaned.append({
                "title": title[:100],
                "text": text,
            })

        return cleaned

    @staticmethod
    def _clean_media(items: list[str]) -> list[str]:
        cleaned: list[str] = []

        for item in items:
            normalized = str(item).strip().replace("\\", "/")
            if not normalized:
                continue

            if normalized.startswith(("http://", "https://")):
                cleaned_value = normalized
            else:
                marker = "uploads/"
                position = normalized.find(marker)
                cleaned_value = (
                    normalized[position:]
                    if position >= 0
                    else normalized.lstrip("/")
                )

            if cleaned_value and cleaned_value not in cleaned:
                cleaned.append(cleaned_value)

        return cleaned

    @staticmethod
    def _clean_title(title: str, text: str) -> str:
        cleaned_title = title.strip()
        if cleaned_title:
            return cleaned_title[:120]

        first_line = next(
            (
                line.strip()
                for line in text.splitlines()
                if line.strip()
            ),
            "Unbenannter Entwurf",
        )
        return first_line[:120]
