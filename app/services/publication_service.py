import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.config import PUBLICATIONS_FILE
from app.models.publication import Publication, utc_now_iso


class PublicationService:
    def __init__(self, file_path: Path = PUBLICATIONS_FILE):
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.file_path.exists():
            self._save_all([])

    def list_publications(
        self,
        post_id: str | None = None,
    ) -> list[Publication]:
        items = self._load_all()

        if post_id:
            items = [item for item in items if item.post_id == post_id]

        return sorted(items, key=lambda item: item.publish_at or "")

    def get(self, publication_id: str) -> Publication | None:
        return next(
            (
                item
                for item in self._load_all()
                if item.id == publication_id
            ),
            None,
        )

    def create_many(
        self,
        *,
        post_id: str,
        assignments: list[dict],
        publish_at: str,
    ) -> list[Publication]:
        """Erstellt pro Seite eine Veröffentlichung mit eigener Textkopie."""
        self._validate_datetime(publish_at)

        items = self._load_all()
        existing = {
            (item.post_id, item.account_id, item.publish_at)
            for item in items
        }
        created: list[Publication] = []
        now = utc_now_iso()

        for assignment in assignments:
            account = assignment["account"]
            key = (post_id, account.id, publish_at)

            if key in existing:
                continue

            publication = Publication(
                id=str(uuid4()),
                post_id=post_id,
                platform=account.platform,
                account_id=account.id,
                account_name=account.name,
                publish_at=publish_at,
                text=str(assignment.get("text", "")).strip(),
                variant_title=(
                    str(assignment.get("variant_title", "")).strip()
                    or "Haupttext"
                ),
                created_at=now,
                updated_at=now,
            )

            items.append(publication)
            created.append(publication)
            existing.add(key)

        if created:
            self._save_all(items)

        return created

    def update(
        self,
        publication_id: str,
        *,
        publish_at: str,
        status: str,
        text: str,
        variant_title: str,
    ) -> Publication | None:
        self._validate_datetime(publish_at)
        items = self._load_all()

        for item in items:
            if item.id != publication_id:
                continue

            item.publish_at = publish_at
            item.status = status
            item.text = text.strip()
            item.variant_title = variant_title.strip() or "Haupttext"
            item.updated_at = utc_now_iso()
            self._save_all(items)
            return item

        return None

    def mark_published(
        self,
        publication_id: str,
        *,
        external_post_id: str,
        published_at: str,
    ) -> Publication | None:
        items = self._load_all()

        for item in items:
            if item.id != publication_id:
                continue

            item.status = "published"
            item.external_post_id = external_post_id
            item.error_message = ""
            item.published_at = published_at
            item.updated_at = utc_now_iso()
            self._save_all(items)
            return item

        return None

    def mark_failed(
        self,
        publication_id: str,
        error_message: str,
    ) -> Publication | None:
        items = self._load_all()

        for item in items:
            if item.id != publication_id:
                continue

            item.status = "failed"
            item.error_message = error_message.strip()[:1000]
            item.updated_at = utc_now_iso()
            self._save_all(items)
            return item

        return None

    def delete(self, publication_id: str) -> bool:
        items = self._load_all()
        remaining = [
            item for item in items if item.id != publication_id
        ]

        if len(remaining) == len(items):
            return False

        self._save_all(remaining)
        return True

    def delete_for_post(self, post_id: str) -> None:
        self._save_all([
            item
            for item in self._load_all()
            if item.post_id != post_id
        ])

    @staticmethod
    def _validate_datetime(value: str) -> None:
        if not value.strip():
            raise ValueError("Bitte Datum und Uhrzeit auswählen.")

        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "Ungültiges Datum oder ungültige Uhrzeit."
            ) from exc

    def _load_all(self) -> list[Publication]:
        try:
            raw = json.loads(
                self.file_path.read_text(encoding="utf-8") or "[]"
            )
        except (OSError, json.JSONDecodeError):
            return []

        return [
            Publication.from_dict(item)
            for item in raw
            if isinstance(item, dict) and item.get("id")
        ]

    def _save_all(self, items: list[Publication]) -> None:
        temporary_file = self.file_path.with_suffix(".tmp")
        temporary_file.write_text(
            json.dumps(
                [item.to_dict() for item in items],
                ensure_ascii=False,
                indent=4,
            ),
            encoding="utf-8",
        )
        temporary_file.replace(self.file_path)
