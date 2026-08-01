import json
from pathlib import Path
from uuid import uuid4

from app.config import SOCIAL_ACCOUNTS_FILE
from app.models.platform import get_platform
from app.models.social_account import SocialAccount
from app.services.settings_service import SettingsService


class SocialAccountService:
    def __init__(
        self,
        file_path: Path = SOCIAL_ACCOUNTS_FILE,
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
        include_inactive: bool = True,
    ) -> list[SocialAccount]:
        accounts = self._load_all()
        accounts = self._merge_connected_accounts(accounts)

        if not include_inactive:
            accounts = [
                account
                for account in accounts
                if account.active
            ]

        return sorted(
            accounts,
            key=lambda account: (
                account.platform,
                account.name.lower(),
            ),
        )

    def grouped_accounts(
        self,
        include_inactive: bool = True,
    ) -> dict[str, list[SocialAccount]]:
        grouped: dict[str, list[SocialAccount]] = {}

        for account in self.list_accounts(
            include_inactive=include_inactive
        ):
            grouped.setdefault(
                account.platform,
                [],
            ).append(account)

        return grouped

    def get(
        self,
        account_id: str,
    ) -> SocialAccount | None:
        return next(
            (
                account
                for account in self.list_accounts()
                if account.id == account_id
            ),
            None,
        )

    def create(
        self,
        *,
        platform: str,
        name: str,
        external_id: str = "",
        username: str = "",
    ) -> SocialAccount:
        platform = platform.strip().lower()
        definition = get_platform(platform)

        if not definition:
            raise ValueError(
                "Diese Plattform wird nicht unterstützt."
            )

        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError(
                "Bitte einen Kontonamen eingeben."
            )

        account = SocialAccount(
            id=str(uuid4()),
            platform=platform,
            name=cleaned_name,
            external_id=external_id.strip(),
            username=username.strip().lstrip("@"),
            active=True,
            connection_status="manual",
            source="manual",
            can_publish=False,
        )

        accounts = self._load_all()
        accounts.append(account)
        self._save_all(accounts)
        return account

    def toggle(
        self,
        account_id: str,
    ) -> bool:
        accounts = self._load_all()

        for account in accounts:
            if account.id != account_id:
                continue

            account.active = not account.active
            self._save_all(accounts)
            return True

        return False

    def delete(
        self,
        account_id: str,
    ) -> bool:
        accounts = self._load_all()
        remaining = [
            account
            for account in accounts
            if account.id != account_id
        ]

        if len(remaining) == len(accounts):
            return False

        self._save_all(remaining)
        return True

    def _merge_connected_accounts(
        self,
        accounts: list[SocialAccount],
    ) -> list[SocialAccount]:
        """Führt alle automatisch verbundenen Plattformkonten zusammen.

        Derzeit werden Facebook-Seiten aus der bestehenden Meta-Verbindung
        eingelesen. Instagram wird im nächsten Schritt hier ergänzt.
        """
        known = {
            (account.platform, account.external_id)
            for account in accounts
            if account.external_id
        }

        for page in SettingsService().load_pages():
            key = ("facebook", page.page_id)

            if key in known:
                continue

            accounts.append(
                SocialAccount(
                    id=f"facebook:{page.page_id}",
                    platform="facebook",
                    name=page.name,
                    external_id=page.page_id,
                    username="",
                    active=True,
                    connection_status="connected",
                    source="meta",
                    can_publish=True,
                )
            )
            known.add(key)

        return accounts

    def _load_all(self) -> list[SocialAccount]:
        try:
            raw = json.loads(
                self.file_path.read_text(
                    encoding="utf-8"
                ) or "[]"
            )
        except (OSError, json.JSONDecodeError):
            return []

        return [
            SocialAccount.from_dict(item)
            for item in raw
            if (
                isinstance(item, dict)
                and item.get("id")
                and item.get("name")
            )
        ]

    def _save_all(
        self,
        accounts: list[SocialAccount],
    ) -> None:
        temporary_file = self.file_path.with_suffix(
            ".tmp"
        )
        temporary_file.write_text(
            json.dumps(
                [
                    account.to_dict()
                    for account in accounts
                ],
                ensure_ascii=False,
                indent=4,
            ),
            encoding="utf-8",
        )
        temporary_file.replace(self.file_path)
