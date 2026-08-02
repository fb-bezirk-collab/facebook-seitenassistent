import json
from pathlib import Path

from app.config import INSTAGRAM_ACCOUNTS_FILE
from app.models.instagram_connection import InstagramConnection


class InstagramAccountService:
    def __init__(self, file_path: Path = INSTAGRAM_ACCOUNTS_FILE):
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self._save_all([])

    def list_accounts(self) -> list[InstagramConnection]:
        try:
            raw = json.loads(self.file_path.read_text(encoding="utf-8") or "[]")
        except (OSError, json.JSONDecodeError):
            return []
        return [
            InstagramConnection.from_dict(item)
            for item in raw
            if isinstance(item, dict) and item.get("instagram_id")
        ]

    def get(self, instagram_id: str) -> InstagramConnection | None:
        return next(
            (item for item in self.list_accounts() if item.instagram_id == instagram_id),
            None,
        )

    def upsert(self, connection: InstagramConnection) -> InstagramConnection:
        items = self.list_accounts()
        replaced = False
        for index, item in enumerate(items):
            if item.instagram_id == connection.instagram_id:
                items[index] = connection
                replaced = True
                break
        if not replaced:
            items.append(connection)
        self._save_all(items)
        return connection

    def _save_all(self, items: list[InstagramConnection]) -> None:
        temp = self.file_path.with_suffix(".tmp")
        temp.write_text(
            json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
        temp.replace(self.file_path)
