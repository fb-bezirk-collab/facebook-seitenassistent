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

    def list_publications(self, post_id: str | None = None) -> list[Publication]:
        items = self._load_all()
        if post_id:
            items = [item for item in items if item.post_id == post_id]
        return sorted(items, key=lambda item: item.publish_at or "")

    def get(self, publication_id: str) -> Publication | None:
        return next((item for item in self._load_all() if item.id == publication_id), None)

    def create(self, *, post_id: str, platform: str, account_id: str, account_name: str, publish_at: str) -> Publication:
        self._validate_datetime(publish_at)
        now = utc_now_iso()
        item = Publication(
            id=str(uuid4()), post_id=post_id, platform=platform,
            account_id=account_id, account_name=account_name,
            publish_at=publish_at, created_at=now, updated_at=now,
        )
        items = self._load_all(); items.append(item); self._save_all(items)
        return item

    def update(self, publication_id: str, *, publish_at: str, status: str) -> Publication | None:
        self._validate_datetime(publish_at)
        items = self._load_all()
        for item in items:
            if item.id == publication_id:
                item.publish_at = publish_at
                item.status = status
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
        remaining = [item for item in items if item.id != publication_id]
        if len(remaining) == len(items): return False
        self._save_all(remaining); return True

    def delete_for_post(self, post_id: str) -> None:
        self._save_all([item for item in self._load_all() if item.post_id != post_id])

    @staticmethod
    def _validate_datetime(value: str) -> None:
        if not value.strip(): raise ValueError("Bitte Datum und Uhrzeit auswählen.")
        try: datetime.fromisoformat(value)
        except ValueError as exc: raise ValueError("Ungültiges Datum oder ungültige Uhrzeit.") from exc

    def _load_all(self) -> list[Publication]:
        try: raw=json.loads(self.file_path.read_text(encoding="utf-8") or "[]")
        except (OSError, json.JSONDecodeError): return []
        return [Publication.from_dict(x) for x in raw if isinstance(x, dict) and x.get("id")]

    def _save_all(self, items: list[Publication]) -> None:
        tmp=self.file_path.with_suffix('.tmp')
        tmp.write_text(json.dumps([x.to_dict() for x in items], ensure_ascii=False, indent=4), encoding='utf-8')
        tmp.replace(self.file_path)
