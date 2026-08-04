import json
from pathlib import Path

from app.config import INSTAGRAM_ACCOUNTS_FILE
from app.models.instagram_connection import InstagramConnection


class InstagramAccountService:
    def __init__(
        self,
        file_path: Path = INSTAGRAM_ACCOUNTS_FILE,
    ):
        self.file_path = file_path
        self.file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.file_path.exists():
            self._save_all([])

    def list_accounts(
        self,
    ) -> list[InstagramConnection]:
        try:
            raw = json.loads(
                self.file_path.read_text(
                    encoding="utf-8",
                )
                or "[]"
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            return []

        return [
            InstagramConnection.from_dict(item)
            for item in raw
            if (
                isinstance(item, dict)
                and item.get("instagram_id")
            )
        ]

    def get(
        self,
        instagram_id: str,
    ) -> InstagramConnection | None:
        return next(
            (
                item
                for item in self.list_accounts()
                if item.instagram_id == instagram_id
            ),
            None,
        )

    def upsert(
        self,
        connection: InstagramConnection,
    ) -> InstagramConnection:
        """Speichert genau einen Eintrag je Instagram-Konto.

        Alte Einträge mit derselben ID, demselben Benutzernamen
        oder derselben Profilbezeichnung werden ersetzt.
        """
        existing_accounts = self.list_accounts()

        username_key = (
            connection.username
            .strip()
            .lower()
            .lstrip("@")
        )

        name_key = (
            connection.name
            .strip()
            .lower()
        )

        kept_accounts: list[
            InstagramConnection
        ] = []

        removed_accounts: list[
            InstagramConnection
        ] = []

        for account in existing_accounts:
            account_username_key = (
                account.username
                .strip()
                .lower()
                .lstrip("@")
            )

            account_name_key = (
                account.name
                .strip()
                .lower()
            )

            same_id = (
                account.instagram_id
                == connection.instagram_id
            )

            same_username = bool(
                username_key
                and account_username_key == username_key
            )

            same_name = bool(
                name_key
                and account_name_key == name_key
            )

            if same_id or same_username or same_name:
                removed_accounts.append(account)
                continue

            kept_accounts.append(account)

        kept_accounts.append(connection)
        self._save_all(kept_accounts)

        for old_account in removed_accounts:
            print(
                "INSTAGRAM_ACCOUNT_UPDATED|"
                f"username={connection.username}|"
                f"old_id={old_account.instagram_id}|"
                f"new_id={connection.instagram_id}",
                flush=True,
            )

        if not removed_accounts:
            print(
                "INSTAGRAM_ACCOUNT_ADDED|"
                f"username={connection.username}|"
                f"id={connection.instagram_id}",
                flush=True,
            )

        return connection

    def _save_all(
        self,
        items: list[InstagramConnection],
    ) -> None:
        temporary_file = (
            self.file_path.with_suffix(".tmp")
        )

        temporary_file.write_text(
            json.dumps(
                [
                    item.to_dict()
                    for item in items
                ],
                ensure_ascii=False,
                indent=4,
            ),
            encoding="utf-8",
        )

        temporary_file.replace(
            self.file_path
        )
